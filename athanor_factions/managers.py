from django.db import models
from django.conf import settings
import evennia
from evennia.typeclasses.managers import TypeclassManager, TypedObjectManager
from evennia.utils import class_from_module
from athanor.utils import Operation, partial_match, validate_name, staff_alert


class FactionDBManager(TypedObjectManager):
    system_name = "FACTION"

    def find_faction(self, operation: Operation, key: str = "faction"):
        if (input := operation.kwargs.get(key, None)) is None:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a Faction ID or Path/Name.")

        if isinstance(input, self.model):
            faction = input
        elif isinstance(input, str):
            path = input.split("/")
            if not len(path):
                operation.status = operation.st.HTTP_400_BAD_REQUEST
                raise operation.ex("You must provide a Faction ID or Path/Name.")

            start_check = path[0]
            rest = path[1:]

            choices = self.filter(db_parent=None)
            if not choices:
                operation.status = operation.st.HTTP_404_NOT_FOUND
                raise operation.ex("No Factions found.")
            if not (choice := partial_match(start_check, choices)):
                operation.status = operation.st.HTTP_404_NOT_FOUND
                raise operation.ex(f"No Faction found called: {start_check}")

            while rest:
                start_check = rest[0]
                rest = rest[1:]
                choices = choice.children.all()
                if not choices:
                    operation.status = operation.st.HTTP_404_NOT_FOUND
                    raise operation.ex(f"No Factions found under: {start_check}")
                if not (new_choice := partial_match(start_check, choices)):
                    operation.status = operation.st.HTTP_404_NOT_FOUND
                    raise operation.ex(f"No Faction found under {choice.full_path()} called: {start_check}")
                choice = new_choice
            else:
                faction = choice

        elif isinstance(input, int):
            faction = self.filter(id=input).first()
            if faction is None:
                operation.status = operation.st.HTTP_404_NOT_FOUND
                raise operation.ex("No Faction found with that ID.")
        else:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a Faction ID or Path/Name.")

        if faction is None:
            operation.status = operation.st.HTTP_404_NOT_FOUND
            raise operation.ex("No Faction found.")

        return faction

    def op_find_faction(self, operation: Operation):
        faction = self.find_faction(operation)
        operation.results = {"success": True, "faction": faction}

    def check_override(self, accessing_obj):
        return accessing_obj.locks.check_lockstring(accessing_obj, settings.FACTION_PERMISSIONS_ADMIN_OVERRIDE)

    def check_admin(self, accessing_obj):
        return (accessing_obj.locks.check_lockstring(accessing_obj, settings.FACTION_PERMISSIONS_ADMIN_MEMBERSHIP) or
                self.check_override(accessing_obj))

    def _validate_name(self, operation: Operation, key="name"):
        if not (
                name := validate_name(
                    operation.kwargs.get(key, None), thing_type="Faction"
                )
        ):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a name for the Faction.")
        return name

    def op_create(self, operation: Operation):
        if not self.check_override(operation.actor):
            operation.status = operation.st.HTTP_403_FORBIDDEN
            raise operation.ex("You do not have permission to create a Faction.")

        name = self._validate_name(operation)
        parent = None

        if "parent" in operation.kwargs:
            parent = self.find_faction(operation, key="parent")

        if exists := self.filter(db_key__iexact=name, db_parent=parent).first():
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex(f"A Faction already exists with that name: {exists}")

        faction = self.create(db_key=name, db_parent=parent)

        message = f"A new Faction was created: {faction.full_path()}."
        operation.results = {"success": True, "faction": faction, "message": message}
        staff_alert(message, operation.actor)

    def op_rename(self, operation: Operation):
        if not self.check_override(operation.actor):
            operation.status = operation.st.HTTP_403_FORBIDDEN
            raise operation.ex("You do not have permission to rename Factions.")

        faction = self.find_faction(operation)

        name = self._validate_name(operation)

        if conflict := self.filter(db_parent=faction.parent, db_key__iexact=name).exclude(id=faction).first():
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex(f"A Faction already exists with that name: {conflict}")

        message = f"{faction.full_path()} was renamed to: {name}."
        faction.key = name
        operation.results = {"success": True, "faction": faction, "message": message}
        staff_alert(message, operation.actor)

    def op_parent(self, operation: Operation):
        if not self.check_override(operation.actor):
            operation.status = operation.st.HTTP_403_FORBIDDEN
            raise operation.ex("You do not have permission to restructure Factions.")

        faction = self.find_faction(operation)

        parent = operation.kwargs.get("parent", None)
        if parent == "/":
            parent = None
        else:
            parent = self.find_faction(operation, key="parent")

        if parent == faction:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("A Faction cannot be its own parent.")

        if parent and faction in parent.ancestors():
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("A Faction cannot be its own ancestor.")

        if faction.contains_sub_faction(parent):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("A Faction cannot be its own descendant.")

        old_path = faction.full_path()
        old_parent = faction.parent
        faction.parent = parent
        new_path = faction.full_path()
        message = f"{old_path} was moved to {new_path}."
        operation.results = {"success": True, "faction": faction, "message": message}
        staff_alert(message, operation.actor)

    def op_config_set(self, operation: Operation):
        faction = self.find_faction(operation)

        if not faction.is_leader(operation.character):
            operation.status = operation.st.HTTP_403_FORBIDDEN
            raise operation.ex("You do not have permission to configure this Faction.")

        try:
            result = faction.options.set(
                operation.kwargs.get("key", None), operation.kwargs.get("value", None)
            )
        except ValueError as err:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex(str(err))

        message = f"Faction '{faction.full_path()}' config '{result.key}' set to '{result.display()}'."
        operation.results = {
            "success": True,
            "faction": faction,
            "message": message,
        }

    def op_config_list(self, operation: Operation):
        faction = self.find_faction(operation)

        if not faction.is_leader(operation.character):
            operation.status = operation.st.HTTP_403_FORBIDDEN
            raise operation.ex("You do not have permission to configure this Faction.")

        config = faction.options.all(return_objs=True)

        out = list()
        for op in config:
            out.append(
                {
                    "name": op.key,
                    "description": op.description,
                    "type": op.__class__.__name__,
                    "value": str(op.display()),
                }
            )

        operation.results = {
            "success": True,
            "faction": faction,
            "config": out,
        }

    def op_list(self, operation: Operation):
        faction = None
        if "faction" in operation.kwargs:
            faction = self.find_faction(operation, key="faction")

        root_factions = self.filter(db_parent=faction)
        factions = [f.serialize(include_children=True) for f in root_factions]
        operation.results = {"success": True, "factions": factions}


class FactionManager(FactionDBManager, TypeclassManager):
    pass


class RankManager(models.Manager):
    system_name = "FACTION"

    def find_faction(self, operation: Operation, key="faction"):
        f = class_from_module(settings.BASE_FACTION_TYPECLASS)
        return f.objects.find_faction(operation, key=key)

    def _validate_name(self, operation: Operation, key="name"):
        if not (
                name := validate_name(
                    operation.kwargs.get(key, None), thing_type="Faction Rank"
                )
        ):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a name for the Rank.")
        return name

    def _validate_rank(self, operation: Operation, key="rank"):
        if not (
                rank := operation.kwargs.get(key, None)
        ):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a Rank number.")
        try:
            rank = int(rank)
        except ValueError as err:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a Rank number.")
        return rank

    def op_create(self, operation: Operation):
        faction = self.find_faction(operation)
        if not faction.is_leader(operation.character):
            operation.status = operation.st.HTTP_403_FORBIDDEN
            raise operation.ex("You do not have permission to create Ranks.")

        rank = self._validate_rank(operation)

        if faction.ranks.filter(number=rank).first():
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("A Rank already exists with that number.")

        name = self._validate_name(operation)

        if faction.ranks.filter(name__iexact=name).first():
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("A Rank already exists with that name.")

        new_rank = faction.ranks.create(name=name, number=rank)

        message = f"Rank {new_rank.number} '{new_rank.name}' created for {faction.full_path()}."
        operation.results = {"success": True, "faction": faction, "rank": new_rank, "message": message}
        staff_alert(message, operation.actor)

    def op_list(self, operation: Operation):
        faction = self.find_faction(operation)
        ranks = faction.ranks.all()
        operation.results = {"success": True, "faction": faction, "ranks": [r.serialize() for r in ranks]}

    def find_rank(self, operation: Operation, faction):
        rank = self._validate_rank(operation)
        if not (rank := faction.ranks.filter(number=rank).first()):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("No Rank found with that number.")
        return rank

    def op_rename(self, operation: Operation):
        faction = self.find_faction(operation)
        if not faction.is_leader(operation.character):
            operation.status = operation.st.HTTP_403_FORBIDDEN
            raise operation.ex("You do not have permission to rename Ranks.")

        rank = self.find_rank(operation, faction)

        name = self._validate_name(operation)

        if conflict := faction.ranks.filter(name__iexact=name).exclude(id=rank).first():
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex(f"A Rank already exists with that name: {conflict}")

        message = f"Rank {rank.number} '{rank.name}' renamed to '{name}'."
        rank.name = name
        rank.save()
        operation.results = {"success": True, "faction": faction, "rank": rank, "message": message}
        staff_alert(message, operation.actor)

    def op_number(self, operation: Operation):
        faction = self.find_faction(operation)
        if not faction.is_leader(operation.character):
            operation.status = operation.st.HTTP_403_FORBIDDEN
            raise operation.ex("You do not have permission to renumber Ranks.")

        rank = self.find_rank(operation, faction)

        new_rank = self._validate_rank(operation, key="new_number")

        if faction.ranks.filter(number=new_rank).first():
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("A Rank already exists with that number.")

        message = f"Rank {rank.number} '{rank.name}' renumbered to '{new_rank}'."
        rank.number = new_rank
        rank.save()
        operation.results = {"success": True, "faction": faction, "rank": rank, "message": message}
        staff_alert(message, operation.actor)

    def op_delete(self, operation: Operation):
        faction = self.find_faction(operation)
        if not faction.is_leader(operation.character):
            operation.status = operation.st.HTTP_403_FORBIDDEN
            raise operation.ex("You do not have permission to delete Ranks.")

        rank = self.find_rank(operation, faction)

        if rank.number <= 2:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You cannot delete the first two Ranks.")

        if rank.holders.count():
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You cannot delete a Rank that has Members.")

        message = f"Rank {rank.number} '{rank.name}' deleted."
        rank.delete()
        operation.results = {"success": True, "faction": faction, "message": message}
        staff_alert(message, operation.actor)

    def op_permissions(self, operation: Operation):
        faction = self.find_faction(operation)
        if not faction.is_leader(operation.character):
            operation.status = operation.st.HTTP_403_FORBIDDEN
            raise operation.ex("You do not have permission to configure Ranks.")

        rank = self.find_rank(operation, faction)

        if not (perm := operation.kwargs.get("permissions", None)):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide Permissions.")

        try:
            permissions = faction.validate_permissions(perm)
        except ValueError as err:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex(str(err))

        rank.data["permissions"] = permissions
        rank.save()
        message = f"Rank {rank.number} '{rank.name}' permissions set to '{permissions}'."
        operation.results = {"success": True, "faction": faction, "rank": rank, "message": message}
        staff_alert(message, operation.actor)


class MemberManager(models.Manager):
    system_name = "FACTION"

    def find_faction(self, operation: Operation, key="faction"):
        f = class_from_module(settings.BASE_FACTION_TYPECLASS)
        return f.objects.find_faction(operation, key=key)

    def _validate_rank(self, operation: Operation, key="rank"):
        if not (
                rank := operation.kwargs.get(key, None)
        ):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a Rank number.")
        try:
            rank = int(rank)
        except ValueError as err:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a Rank number.")
        return rank

    def find_rank(self, operation: Operation, faction, key="rank"):
        rank = self._validate_rank(operation, key=key)
        rank = faction.ranks.filter(number=rank).first()
        if not rank:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("No Rank found with that number.")
        return rank

    def op_list(self, operation: Operation):
        faction = self.find_faction(operation)
        members = faction.members.all()
        operation.results = {"success": True, "faction": faction, "members": [m.serialize() for m in members]}

    def find_character(self, operation: Operation, key="character"):
        if not (character := operation.kwargs.get(key, None)):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a Character.")
        if not isinstance(character, evennia.ObjectDB):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a Character.")
        return character

    def op_add(self, operation: Operation):
        faction = self.find_faction(operation)
        if not faction.__class_.objects.check_admin(operation.character):
            operation.status = operation.st.HTTP_403_FORBIDDEN
            raise operation.ex("You do not have permission to add Members.")

        character = operation.kwargs.get("character", None)
        if not character:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a Character.")

        if not (character := self.find_character(operation)):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("No Character found.")

        if "rank" not in operation.kwargs:
            operation.kwargs["rank"] = faction.options.get("start_rank")

        rank = self.find_rank(operation, faction)

        if faction.members.filter(character=character).first():
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("That Character is already a Member.")

        faction.members.create(character=character, rank=rank)

        message = f"{character} added to {faction.full_path()} as Rank {rank.number} '{rank.name}'."
        operation.results = {"success": True, "faction": faction, "character": character, "rank": rank, "message": message}
        staff_alert(message, operation.actor)

    def op_remove(self, operation: Operation):
        faction = self.find_faction(operation)
        if not faction.has_permission(operation.character, "roster"):
            operation.status = operation.st.HTTP_403_FORBIDDEN
            raise operation.ex("You do not have permission to remove Members.")

        character = self.find_character("character")

        if not (member := faction.members.filter(character=character).first()):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("That Character is not a Member.")

        rank = faction.get_effective_rank(operation.character)
        if rank.number > member.rank.number:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You cannot remove a Member of equal or higher Rank.")

        message = f"{character} removed from {faction.full_path()}."
        member.delete()
        operation.results = {"success": True, "faction": faction, "character": character, "message": message}
        staff_alert(message, operation.actor)

    def op_rank(self, operation: Operation):
        faction = self.find_faction(operation)
        if not faction.has_permission(operation.character, "roster"):
            operation.status = operation.st.HTTP_403_FORBIDDEN
            raise operation.ex("You do not have permission to promote Members.")

        character = self.find_character("character")

        if not (member := faction.members.filter(character=character).first()):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("That Character is not a Member.")

        rank = self.find_rank(operation, faction)

        actor_rank = faction.get_effective_rank(operation.character)

        if actor_rank.number > member.rank.number:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You cannot promote a Member of equal or higher Rank.")

        if rank.number >= member.rank.number:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You cannot promote a Member to equal or higher Rank.")

        message = f"{character} promoted to Rank {rank.number} '{rank.name}' in {faction.full_path()}."
        member.rank = rank
        member.save()
        operation.results = {"success": True, "faction": faction, "character": character, "rank": rank, "message": message}
        staff_alert(message, operation.actor)

    def op_permissions(self, operation: Operation):
        faction = self.find_faction(operation)
        if not faction.is_leader(operation.character):
            operation.status = operation.st.HTTP_403_FORBIDDEN
            raise operation.ex("You do not have permission to alter Member permissions.")

        character = self.find_character("character")

        if not (member := faction.members.filter(character=character).first()):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("That Character is not a Member.")

        if not (perm := operation.kwargs.get("permissions", None)):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide Permissions.")

        try:
            permissions = faction.validate_permissions(perm)
        except ValueError as err:
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex(str(err))

        member.data["permissions"] = permissions
        member.save()
        message = f"{character} permissions set to '{permissions}' for {faction.full_path()}."
        operation.results = {"success": True, "faction": faction, "character": character, "message": message}
        staff_alert(message, operation.actor)

    def op_title(self, operation: Operation):
        """
        Sets the title of a Member.
        This is stored in their .data["title"] attribute.
        """
        faction = self.find_faction(operation)
        if not faction.has_permission(operation.character, "roster"):
            operation.status = operation.st.HTTP_403_FORBIDDEN
            raise operation.ex("You do not have permission to set Member titles.")

        character = self.find_character("character")

        if not (member := faction.members.filter(character=character).first()):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("That Character is not a Member.")

        my_rank = faction.get_effective_rank(operation.character)
        if (my_rank.number >= member.rank.number) and not (operation.character == member.character):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You cannot set the title of a Member of equal or higher Rank.")

        if not (title := operation.kwargs.get("title", None)):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a title.")

        member.data["title"] = title
        member.save()
        message = f"{character} title set to '{title}' for {faction.full_path()}."
        operation.results = {"success": True, "faction": faction, "character": character, "message": message}
        staff_alert(message, operation.actor)


class InvitationManager(models.Manager):
    system_name = "FACTION"

    def find_faction(self, operation: Operation, key="faction"):
        f = class_from_module(settings.BASE_FACTION_TYPECLASS)
        return f.objects.find_faction(operation, key=key)

    def find_character(self, operation: Operation, key="character"):
        if not (character := operation.kwargs.get(key, None)):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a Character.")
        if not isinstance(character, evennia.ObjectDB):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You must provide a Character.")
        return character

    def op_extend(self, operation: Operation):
        faction = self.find_faction(operation)
        if not faction.has_permission(operation.character, "invite"):
            operation.status = operation.st.HTTP_403_FORBIDDEN
            raise operation.ex("You do not have permission to invite Members.")

        character = self.find_character(operation)

        if faction.members.filter(character=character).first():
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("That Character is already a Member.")

        if faction.invitations.filter(character=character).first():
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("That Character already has an Invitation.")

        faction.invitations.create(character=character)

        message = f"{character} invited to {faction.full_path()}."
        character.msg(f"You have been invited to join {faction.full_path()}. help fiaccept for more information.")
        operation.results = {"success": True, "faction": faction, "character": character, "message": message}
        staff_alert(message, operation.actor)

    def op_rescind(self, operation: Operation):
        faction = self.find_faction(operation)
        if not faction.has_permission(operation.character, "invite"):
            operation.status = operation.st.HTTP_403_FORBIDDEN
            raise operation.ex("You do not have permission to rescind Invitations.")

        character = self.find_character(operation)

        if not (invitation := faction.invitations.filter(character=character).first()):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("That Character does not have an Invitation.")

        message = f"{character} invitation to {faction.full_path()} rescinded."
        invitation.delete()
        character.msg(f"Your invitation to join {faction.full_path()} has been rescinded.")
        operation.results = {"success": True, "faction": faction, "character": character, "message": message}
        staff_alert(message, operation.actor)

    def op_list(self, operation: Operation):
        faction = self.find_faction(operation)
        invitations = faction.invitations.all()
        operation.results = {"success": True, "faction": faction, "invitations": [i.serialize() for i in invitations]}

    def op_accept(self, operation: Operation):
        faction = self.find_faction(operation)
        character = operation.character

        if not (invitation := faction.invitations.filter(character=character).first()):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You do not have an Invitation to that Faction.")

        if faction.members.filter(character=character).first():
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You are already a Member of that Faction.")

        start_rank = faction.options.get("start_rank")

        if not (rank := faction.ranks.filter(number=start_rank).first()):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex(f"That Faction does not have a Rank {start_rank}.")

        faction.members.create(character=character, rank=rank)
        invitation.delete()
        message = f"{character} joined {faction.full_path()} as Rank {rank.number} '{rank.name}'."
        character.msg(f"You have joined {faction.full_path()} as Rank {rank.number} '{rank.name}'.")
        operation.results = {"success": True, "faction": faction, "character": character, "message": message}
        staff_alert(message, operation.actor)

    def op_reject(self, operation: Operation):
        faction = self.find_faction(operation)
        character = operation.character

        if not (invitation := faction.invitations.filter(character=character).first()):
            operation.status = operation.st.HTTP_400_BAD_REQUEST
            raise operation.ex("You do not have an Invitation to that Faction.")

        invitation.delete()
        message = f"{character} rejected invitation to {faction.full_path()}."
        character.msg(f"You have rejected the invitation to join {faction.full_path()}.")
        operation.results = {"success": True, "faction": faction, "character": character, "message": message}
        staff_alert(message, operation.actor)