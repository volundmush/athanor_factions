import athanor
from collections import defaultdict


def init(settings, plugins: dict):
    settings.BASE_FACTION_TYPECLASS = "athanor_factions.factions.DefaultFaction"
    settings.INSTALLED_APPS.append("athanor_factions")

    settings.LOCK_FUNC_MODULES.append("athanor_factions.lockfuncs")
    settings.OPTION_CLASS_MODULES.append("athanor_factions.options")

    settings.FACTION_PERMISSIONS_BUILTIN = {"roster", "invite", "discipline"}

    settings.OPTIONS_FACTION_DEFAULT = {
        "universal_permissions": ["Permissions granted to all members of the faction.", "FactionPermissions", ""],
        "permissions": ["Custom Permissions added to the faction beyond builtins.", "FactionPermissions", ""],
        "sub_permissions": ["Permissions extended to sub-factions of this faction.", "FactionPermissions", ""],
        "start_rank": ["Number of Starting Rank for invited characters.", "PositiveInteger", 5],
    }

    settings.FACTION_ACCESS_FUNCTIONS = defaultdict(list)

    # Whoever passes this lockstring has complete control over all Factions, including
    # the rights to create, delete, re-parent, etc, them.
    settings.FACTION_PERMISSIONS_ADMIN_OVERRIDE = "perm(Developer)"

    # Whoever passes this lock is considered a Rank 0 member of all Factions, and holds
    # all possible permissions within those factions.
    settings.FACTION_PERMISSIONS_ADMIN_MEMBERSHIP = "perm(Admin)"

    athanor.FACTION_ACCESS_FUNCTIONS = defaultdict(list)
    settings.ACCESS_FUNCTIONS_LIST.append("FACTION")
    settings.AT_SERVER_STARTSTOP_MODULE.append("athanor_factions.startup_hooks")

    # This data must be convertible to JSON; "name" will be .pop()'d and
    # everything else shoved in the Rank's .data field.
    settings.FACTION_DEFAULT_RANKS = {
        1: {"name": "Leader", "permissions": ["roster", "invite", "discipline"]},
        2: {"name": "Second", "permissions": ["roster", "invite", "discipline"]},
        3: {"name": "Officer", "permissions": ["invite", "discipline"]},
        4: {"name": "Member", "permissions": []},
        5: {"name": "Recruit", "permissions": []},
    }

    settings.CMD_MODULES_CHARACTER.append("athanor_factions.commands")