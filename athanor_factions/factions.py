import typing

from django.conf import settings

from evennia.typeclasses.models import TypeclassBase
from evennia.utils.optionhandler import OptionHandler
from evennia.utils.utils import lazy_property

import athanor
from athanor.utils import partial_match
from athanor.typeclasses.mixin import AthanorAccess

from .managers import FactionManager
from .models import FactionDB, Member


class DefaultFaction(AthanorAccess, FactionDB, metaclass=TypeclassBase):
    system_name = "FACTION"
    objects = FactionManager()
    lock_access_functions = athanor.FACTION_ACCESS_FUNCTIONS

    def at_first_save(self):
        for rank, data in settings.FACTION_DEFAULT_RANKS.items():
            name = data.pop("name", "")
            self.ranks.create(name=name, number=rank, data=data)

    def contains_sub_faction(self, faction):
        for child in self.children.all():
            if child == faction:
                return True
            if child.contains_sub_faction(faction):
                return True
        return False

    def ancestors(self):
        if self.parent:
            yield self.parent
            yield from self.parent.ancestors()

    def full_path(self):
        chain = [self]
        for ancestor in self.ancestors():
            chain.append(ancestor)
        return "/".join([f.key for f in reversed(chain)])

    def is_deleted(self):
        if self.deleted:
            return True
        if self.parent:
            return self.parent.is_deleted()
        return False

    def serialize(self, include_parent=False, include_children=False):
        out = {
            "id": self.id,
            "key": self.key
        }

        if include_parent and self.parent and not self.parent.deleted:
            out["parent"] = self.parent.serialize(include_parent=True)

        if include_children:
            out["children"] = [child.serialize(include_parent=False, include_children=True) for child in
                               self.children.filter(db_deleted=False)]

        return out

    @lazy_property
    def options(self):
        return OptionHandler(self,
                             options_dict=settings.OPTIONS_FACTION_DEFAULT,
                             savefunc=self.attributes.add,
                             loadfunc=self.attributes.get,
                             save_kwargs={"category": "option"},
                             load_kwargs={"category": "option"},
                             )

    def is_member(self, character, check_admin: bool = True) -> bool:
        if check_admin:
            if self.__class__.objects.check_admin(character):
                return True
        if Member.objects.filter(character=character, rank__faction=self).exists():
            return True
        for child in self.children.all():
            if child.is_member(character, check_admin=False):
                return True
        return False

    def get_effective_rank(self, character) -> typing.Optional[int]:
        if self.__class__.objects.check_admin(character):
            return 0
        if member := Member.objects.filter(character=character, rank__faction=self).first():
            return member.rank.number
        return None

    def is_leader(self, character) -> bool:
        rank = self.get_effective_rank(character)
        if rank is None:
            return False
        return rank <= 1

    def join_permissions(self, perm_sets: list[set[str]]):
        out = set()
        for perm_set in perm_sets:
            out.update(perm_set)
        return {v for val in out if (v := val.strip().lower())}

    def all_permissions(self) -> set[str]:
        return self.join_permissions([self.options.get("permissions", set()),
                                      settings.FACTION_PERMISSIONS_BUILTIN])

    def get_effective_permissions(self, character) -> set[str]:
        all_permissions = self.all_permissions()

        if self.__class__.objects.check_admin(character):
            return all_permissions

        if member := Member.objects.filter(character=character, rank__faction=self).first():
            if member.rank.number <= 1:
                return all_permissions
            out = list()
            out.append(self.options.get("universal_permissions", set()))
            if rank_permissions := member.rank.data.get("permissions", set()):
                out.append(rank_permissions)
            if member_permissions := member.data.get("permissions", set()):
                out.append(member_permissions)
            return self.join_permissions(out).intersection(all_permissions)

        if self.is_sub_member(character):
            return self.join_permissions([self.options.get("sub_permissions", set())]).intersection(all_permissions)

        return set()

    def has_permission(self, character, permission: str):
        rank = self.get_effective_rank(character)
        if rank is None:
            return False
        if rank <= 1:
            return True
        permissions = self.get_effective_permissions(character)
        return permission.strip().lower() in permissions

    def validate_permissions(self, perms: str):
        try:
            entered_permissions = perms.lower().split()
        except Exception as err:
            raise ValueError("Must enter a permission string!")

        out_permissions = set()

        all_permissions = self.all_permissions()

        for perm in entered_permissions:
            if not (found_perm := partial_match(perm, all_permissions)):
                raise ValueError(f"Permission {perm} not found! Choices: {all_permissions}")
            out_permissions.add(found_perm)

        return list(out_permissions)