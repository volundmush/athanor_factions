from django.conf import settings
from evennia.utils import class_from_module, lazy_property
from athanor.utils import Operation

from .models import Member, Rank

_TYPECLASS = None


class _LockFunctionHelper:

    def __init__(self, accessing_obj, accessed_obj, path=None, **kwargs):
        self.accessing_obj = accessing_obj
        self.accessed_obj = accessed_obj
        self.path = path
        self.kwargs = kwargs
        self.faction = None

    @property
    def typeclass(self):
        global _TYPECLASS
        if _TYPECLASS is None:
            _TYPECLASS = class_from_module(settings.BASE_FACTION_TYPECLASS)
        return _TYPECLASS

    def prepare(self) -> bool:
        if not hasattr(self.accessing_obj, "at_post_puppet"):
            return False

        if not self.path:
            return hasattr(self.accessed_obj, "is_member")

        op = Operation(
            user=self.accessing_obj.account,
            character=self.accessing_obj,
            target=self.typeclass.objects,
            operation="find_faction",
            kwargs={"faction": self.path}
        )
        op.execute()

        self.faction = op.results.get("faction", None)

        return self.faction is not None


def fmember(accessing_obj: "DefaultCharacter", accessed_obj, *args, **kwargs):
    """
    Usage:
      fmember(<faction name or ID>)

    This lock checks for membership in a given faction. It directly calls
    the relevant faction's .is_member(character) method.

    If that function cannot be called for any reason,
    the lock will fail.

    If set ON a faction, then going without a name will result in the faction being checked.
    Including args will do a name lookup instead.
    """
    path = args[0] if args else None
    helper = _LockFunctionHelper(accessing_obj, accessed_obj, path, **kwargs)
    if not helper.prepare():
        return False
    return helper.faction.is_member(accessing_obj)


def frank(accessing_obj: "DefaultCharacter", accessed_obj, *args, **kwargs):
    """
    Usage:
      frank(<faction name or ID>, <rank to meet or exceed: int>)
      frank(<rank to meet or exceed: int>)

    This lock checks for the rank of a character in a given faction.

    With two arguments, it will check a specific faction.
    The one argument variant can only be used if the accessed_obj is the faction.
    """
    if not args:
        return False
    path = args[0] if len(args) > 1 else None
    helper = _LockFunctionHelper(accessing_obj, accessed_obj, path, **kwargs)
    if not helper.prepare():
        return False
    if (rank := helper.faction.get_effective_rank(accessing_obj)) is None:
        return False
    to_meet = args[1] if len(args) > 1 else args[0]

    try:
        to_meet = int(to_meet)
    except ValueError:
        return False

    return rank >= to_meet


def fperm(accessing_obj: "DefaultCharacter", accessed_obj, *args, **kwargs):
    """
    Usage:
      fperm(<faction name or ID>, <permission to check for>)
      fperm(<permission to check for>)

    This lock checks for the permissions of a character in a given faction.

    With two arguments, it will check a specific faction.
    The one argument variant can only be used if the accessed_obj is the faction.
    """
    if not args:
        return False
    path = args[0] if len(args) > 1 else None
    helper = _LockFunctionHelper(accessing_obj, accessed_obj, path, **kwargs)
    if not helper.prepare():
        return False
    perm = args[1] if len(args) > 1 else args[0]
    return perm.lower() in helper.faction.get_effective_permissions(accessing_obj)
