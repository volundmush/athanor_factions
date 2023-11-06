from django.conf import settings

from athanor.commands import AthanorCommand
from evennia.utils import class_from_module

from .models import Rank, Member, Invitation
from rich.tree import Tree


class _FCmd(AthanorCommand):
    help_category = "Factions"

    @property
    def f(self):
        return class_from_module(settings.BASE_FACTION_TYPECLASS)

    def build_tree(self, branch, data):
        for f in data:
            new_branch = branch.add(f.get("key"))
            if children := f.get("children", list()):
                self.build_tree(new_branch, children)


class _FAdmin(_FCmd):
    locks = f"cmd:{settings.FACTION_PERMISSIONS_ADMIN_OVERRIDE}"


class CmdFCreate(_FAdmin):
    """
    Create a Faction.

    Syntax:
        fcreate <name>[=<parent path>]

    Creates a new Faction. If no parent is specified, the new Faction will be a top-level Faction.

    Faction names must be unique (case-insensitive) per-parent.
    """
    key = "fcreate"

    def func(self):
        if not self.lhs:
            self.msg("Usage: fcreate <name>[=<parent path>]")
            return

        kwargs = {"name": self.lhs}
        if (parent := self.rhs if self.rhs else None):
            kwargs["parent"] = parent

        op = self.operation(
            target=self.f.objects,
            operation="create",
            kwargs=kwargs,
        )
        op.execute()
        self.op_message(op)


class CmdFRename(_FAdmin):
    """
    Rename a Faction.

    Syntax:
        frename <path> = <new name>

    Faction names must be unique per-parent, case-insensitive.
    This can be used to correct a faction name's casing, though.
    """
    key = "frename"

    def func(self):
        if not self.lhs and self.rhs:
            self.msg("Usage: frename <path> = <new name>")
            return

        op = self.operation(
            target=self.f.objects,
            operation="rename",
            kwargs={
                "faction": self.lhs,
                "name": self.rhs,
            },
        )
        op.execute()
        self.op_message(op)


class CmdFParent(_FAdmin):
    """
    Change a Faction's parent.

    Syntax:
        fparent <path> = <new parent path>

    To make a parent a root faction, use / for the new parent path.
    """
    key = "fparent"

    def func(self):
        if not self.lhs and self.rhs:
            self.msg("Usage: fparent <path> = <new parent path>")
            return

        op = self.operation(
            target=self.f.objects,
            operation="parent",
            kwargs={
                "faction": self.lhs,
                "parent": self.rhs,
            },
        )
        op.execute()
        self.op_message(op)


class CmdFDelete(_FAdmin):
    """
    Delete a Faction.

    Syntax:
        fdelete <path>=<name>

    This will delete the Faction and all sub-factions.

    The full name must be included for verification.

    This can only be undone by developers, so beware.
    """
    key = "fdelete"

    def func(self):
        if not self.rhs and self.lhs:
            self.msg("Usage: fdelete <path>=<name>")
            return

        op = self.operation(
            target=self.f.objects,
            operation="delete",
            kwargs={
                "faction": self.self.lhs,
                "name": self.rhs
            },
        )
        op.execute()
        self.op_message(op)


class CmdFSelect(_FCmd):
    """
    Select a Faction.

    Syntax:
        fselect <path>

    This will select the specified Faction for further commands.
    """
    key = "fselect"

    def func(self):
        if not self.args:
            self.msg("Usage: fselect <path>")
            selected = self.caller.attributes.get("selected", category="faction", default=None)
            if selected:
                self.msg(f"Currently selected: {selected.full_path()}")
            return

        op = self.operation(
            target=self.f.objects,
            operation="find_faction",
            kwargs={
                "faction": self.args,
            },
        )
        op.execute()

        if not op.results.get("success", False):
            self.op_message(op)
            return

        faction = op.results.get("faction")
        self.caller.msg(f"Faction selected: {faction.full_path()}")

        self.caller.attributes.add("selected", category="faction", value=faction)


class _FCmdSelected(_FCmd):
    must_select = True

    def at_pre_cmd(self):
        if (results := super().at_pre_cmd()) is not None:
            return results
        self.selected = self.caller.attributes.get("selected", category="faction", default=None)
        if self.must_select and not self.selected:
            self.msg("No Faction selected. Use fselect <path> to select a faction.")
            return True


class CmdFConfig(_FCmdSelected):
    """
    Configure the selected Faction.

    Syntax:
        fconfig
        fconfig <key> = <value>

    If no key is specified, the current configuration will be displayed.
    The second form is used to set options.
    """
    key = "fconfig"

    def func(self):
        if self.args:
            self.set_config()
        else:
            self.list_config()

    def set_config(self):
        if not self.lhs and self.rhs:
            self.msg("Usage: fconfig <key> = <value>")
            return

        op = self.operation(
            target=self.f.objects,
            operation="config_set",
            kwargs={
                "faction": self.selected,
                "key": self.lhs,
                "value": self.rhs,
            },
        )
        op.execute()
        self.op_message(op)

    def list_config(self):

        op = self.operation(
            target=self.f.objects,
            operation="config_list",
            kwargs={
                "faction": self.selected,
            },
        )
        op.execute()

        if not op.results.get("success", False):
            self.op_message(op)
            return

        if not (data := op.results.get("config", list())):
            self.msg("No configuration found.")
            return

        f = op.results.get("faction")

        t = self.rich_table(
            "Name",
            "Description",
            "Type",
            "Value",
            title=f"'{f.full_path()}' Config Options",
        )
        for config in data:
            t.add_row(
                config["name"], config["description"], config["type"], config["value"]
            )
        self.buffer.append(t)


class CmdFList(_FCmd):
    """
    List Factions.

    Syntax:
        flist
        flist <path>

    If no path is specified, the top-level Factions will be listed.
    Otherwise, it lists factions under the specified path.
    """
    key = "flist"
    aliases = ["factions"]

    def func(self):
        faction = None
        kwargs = dict()
        if self.args:
            op_find = self.operation(
                target=self.f.objects,
                operation="find_faction",
                kwargs={
                    "faction": self.args,
                },
            )
            op_find.execute()
            if not op_find.results.get("success", False):
                self.op_message(op_find)
                return
            faction = op_find.results.get("faction")
            kwargs['faction'] = faction

        op = self.operation(
            target=self.f.objects,
            operation="list",
            kwargs=kwargs,
        )
        op.execute()

        if not op.results.get("success", False):
            self.op_message(op)
            return

        if not (factions := op.results.get("factions", list())):
            self.msg("No factions found.")
            return

        label = "Top-Level Factions" if not faction else f"Sub-Factions of '{faction.full_path()}'"
        t = Tree(label)

        self.build_tree(t, factions)
        self.buffer.append(t)


class CmdFaction(_FCmd):
    """
    Displays basic information about a faction.

    Syntax:
        faction <path>
    """
    key = "faction"

    def func(self):
        if not self.args:
            self.msg("Usage: faction <path>")
            return

        op = self.operation(
            target=self.f.objects,
            operation="find_faction",
            kwargs={
                "faction": self.args,
            },
        )
        op.execute()

        if not op.results.get("success", False):
            self.op_message(op)
            return

        faction = op.results.get("faction")

        t = self.rich_table("Name", "Rank", "Title", "Status", title=f"'Faction: {faction.full_path()}'")
        for member in Member.objects.filter(rank__faction=faction).order_by("rank__number", "character__db_key"):
            t.add_row(member.character.key, f"{member.rank.number}: {member.rank.name}", member.data.get("title", ""),
                      "")

        self.buffer.append(t)
        if not (children := faction.children.all()):
            return

        tr = Tree("Sub-Factions")
        self.build_tree(tr, [f.serialize(include_children=True) for f in children])
        self.buffer.append(tr)


class CmdFRList(_FCmdSelected):
    """
    List the ranks of the selected faction.

    Syntax:
        frlist [<path>]

    Will show the currently selected faction if no path is given.
    """
    key = "frlist"
    must_select = False

    def func(self):
        kwargs = dict()
        if self.args:
            kwargs['faction'] = self.args
        else:
            kwargs['faction'] = self.selected

        op = self.operation(
            target=Rank.objects,
            operation="list",
            kwargs=kwargs,
        )
        op.execute()

        if not op.results.get("success", False):
            self.op_message(op)
            return

        faction = op.results.get("faction")

        if not (ranks := op.results.get("ranks", list())):
            self.msg("No ranks found.")
            return

        t = self.rich_table("Number", "Name", "Permissions", title=f"'{faction.full_path()}' Ranks")
        for rank in ranks:
            data = rank.get("data", dict())
            t.add_row(str(rank["number"]), rank["name"], " ".join(data.get("permissions", [])))
        self.buffer.append(t)


class CmdFRCreate(_FCmdSelected):
    """
    Create a rank for the selected faction.

    Syntax:
        frcreate <number>=name

    If no number is specified, the rank will be created at the bottom of the list.
    """
    key = "frcreate"

    def func(self):
        if not self.lhs and self.rhs:
            self.msg("Usage: frcreate <number>=<name>")
            return

        op = self.operation(
            target=Rank.objects,
            operation="create",
            kwargs={
                "faction": self.selected,
                "rank": self.lhs,
                "name": self.rhs,
            },
        )
        op.execute()
        self.op_message(op)


class CmdFRDelete(_FCmdSelected):
    """
    Delete a rank from the selected faction.

    Syntax:
        frdelete <number>

    This will delete the rank and remove it from all members.
    """
    key = "frdelete"

    def func(self):
        if not self.args:
            self.msg("Usage: frdelete <number>")
            return

        op = self.operation(
            target=Rank.objects,
            operation="delete",
            kwargs={
                "faction": self.selected,
                "rank": self.args,
            },
        )
        op.execute()
        self.op_message(op)


class CmdFRNumber(_FCmdSelected):
    """
    Change the number of a rank.

    Syntax:
        frnumber <number> = <new number>

    This will shift the rank to the new number.
    """
    key = "frnumber"

    def func(self):
        if not self.lhs and self.rhs:
            self.msg("Usage: frnumber <number> = <new number>")
            return

        op = self.operation(
            target=Rank.objects,
            operation="number",
            kwargs={
                "faction": self.selected,
                "rank": self.lhs,
                "new_number": self.rhs,
            },
        )
        op.execute()
        self.op_message(op)


class CmdFRName(_FCmdSelected):
    """
    Change the name of a rank.

    Syntax:
        frname <number> = <new name>

    This will change the name of the rank.
    """
    key = "frname"

    def func(self):
        if not self.lhs and self.rhs:
            self.msg("Usage: frname <number> = <new name>")
            return

        op = self.operation(
            target=Rank.objects,
            operation="rename",
            kwargs={
                "faction": self.selected,
                "rank": self.lhs,
                "name": self.rhs,
            },
        )
        op.execute()
        self.op_message(op)


class CmdFRPerm(_FCmdSelected):
    """
    Change the permissions of a rank.

    Syntax:
        frperm <number> = <permissions>
    """
    key = "frperm"

    def func(self):
        if not self.lhs and self.rhs:
            self.msg("Usage: frperm <number> = <permissions>")
            return

        op = self.operation(
            target=Rank.objects,
            operation="permissions",
            kwargs={
                "faction": self.selected,
                "rank": self.lhs,
                "permissions": self.rhs,
            },
        )
        op.execute()
        self.op_message(op)


class CmdFIExtend(_FCmdSelected):
    """
    Extend an invitation to a character.

    Syntax:
        fiextend <character>[=<faction path>]
    """
    key = "fiextend"
    must_select = False

    def func(self):
        if not self.lhs:
            self.msg("Usage: fiextend <character>[=<faction path>]")
            return

        kwargs = {"character": self.lhs}
        if self.rhs:
            kwargs["faction"] = self.rhs
        else:
            kwargs["faction"] = self.selected

        op = self.operation(
            target=Invitation.objects,
            operation="extend",
            kwargs=kwargs,
        )
        op.execute()
        self.op_message(op)


class CmdFIRescind(_FCmdSelected):
    """
    Rescind an invitation to a character.

    Syntax:
        firescind <character>[=<faction path>]
    """
    key = "firescind"
    must_select = False

    def func(self):
        if not self.lhs:
            self.msg("Usage: firescind <character>[=<faction path>]")
            return

        kwargs = {"character": self.lhs}
        if self.rhs:
            kwargs["faction"] = self.rhs
        else:
            kwargs["faction"] = self.selected

        op = self.operation(
            target=Invitation.objects,
            operation="rescind",
            kwargs=kwargs,
        )
        op.execute()
        self.op_message(op)


class CmdFIAccept(_FCmd):
    """
    Accept an invitation to join a faction.

    Syntax:
        fiaccept <faction path>
    """
    key = "fiaccept"

    def func(self):
        if not self.args:
            self.msg("Usage: fiaccept <faction path>")
            return

        op = self.operation(
            target=Invitation.objects,
            operation="accept",
            kwargs={
                "character": self.caller,
                "faction": self.args,
            },
        )
        op.execute()
        self.op_message(op)


class CmdFIReject(_FCmd):
    """
    Reject an invitation to join a faction.

    Syntax:
        fireject <faction path>
    """
    key = "fireject"

    def func(self):
        if not self.args:
            self.msg("Usage: fireject <faction path>")
            return

        op = self.operation(
            target=Invitation.objects,
            operation="reject",
            kwargs={
                "character": self.caller,
                "faction": self.args,
            },
        )
        op.execute()
        self.op_message(op)


class CmdFIList(_FCmdSelected):
    """
    List invitations to the selected faction.
    Or the given faction.

    Syntax:
        filist [<faction path>]
    """
    key = "filist"
    must_select = False

    def func(self):
        kwargs = dict()
        if self.args:
            kwargs["faction"] = self.args
        else:
            kwargs["faction"] = self.selected

        op = self.operation(
            target=Invitation.objects,
            operation="list",
            kwargs=kwargs,
        )
        op.execute()

        if not op.results.get("success", False):
            self.op_message(op)
            return

        if not (invitations := op.results.get("invitations", list())):
            self.msg("No invitations found.")
            return

        t = self.rich_table("Character", "Inviter", title=f"'{op.results.get('faction').full_path()}' Invitations")
        for invitation in invitations:
            t.add_row(invitation["character"], invitation["inviter"])
        self.buffer.append(t)