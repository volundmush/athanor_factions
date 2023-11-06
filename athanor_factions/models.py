from django.db import models
from django.conf import settings
from evennia.typeclasses.models import TypedObject
from .managers import FactionDBManager, RankManager, MemberManager, InvitationManager


class FactionDB(TypedObject):
    objects = FactionDBManager()

    __settingsclasspath__ = settings.BASE_FACTION_TYPECLASS
    __defaultclasspath__ = "athanor_factions.factions.DefaultFaction"
    __applabel__ = "athanor_factions"

    db_parent = models.ForeignKey("self", related_name="children", null=True, blank=True, on_delete=models.PROTECT)
    db_deleted = models.BooleanField(default=False)

    def __str__(self):
        return self.key


class Rank(models.Model):
    objects = RankManager()

    faction = models.ForeignKey(
        FactionDB, on_delete=models.CASCADE, related_name="ranks"
    )
    name = models.CharField(max_length=255, null=False, blank=False)
    number = models.IntegerField(null=False)
    data = models.JSONField(null=False, default=dict)

    def __repr__(self):
        return f"<{self.faction.full_path()}'s Rank {self.number}: {self.name}>"

    def serialize(self):
        return {
            "name": self.name,
            "number": self.number,
            "data": self.data,
        }

    class Meta:
        ordering = ["faction", "number"]
        unique_together = (("faction", "name"), ("faction", "number"))


class Member(models.Model):
    objects = MemberManager()
    character = models.ForeignKey(
        "objects.ObjectDB", related_name="faction_ranks", on_delete=models.CASCADE
    )
    rank = models.ForeignKey(Rank, related_name="holders", on_delete=models.PROTECT)
    data = models.JSONField(null=False, default=dict)

    def __str__(self):
        return str(self.character)

    def __repr__(self):
        return f"<Rank {self.rank.number} Member of {self.rank.faction.full_path()}: {self.character}>"

    def serialize(self):
        return {
            "character": self.character.key,
            "rank": self.rank.serialize(),
            "data": self.data,
        }

    class Meta:
        ordering = ["rank__faction", "rank__number", "character__db_key"]


class Invitation(models.Model):
    objects = InvitationManager()

    character = models.ForeignKey("objects.ObjectDB", related_name="faction_invitations", on_delete=models.CASCADE)
    faction = models.ForeignKey(FactionDB, related_name="invitations", on_delete=models.CASCADE)
    inviter = models.ForeignKey("objects.ObjectDB", related_name="faction_invitations_extended",
                                on_delete=models.CASCADE)

    class Meta:
        unique_together = (("character", "faction"),)

    def serialize(self):
        return {
            "character": self.character.key,
            "faction": self.faction.id,
            "inviter": self.inviter.key,
        }