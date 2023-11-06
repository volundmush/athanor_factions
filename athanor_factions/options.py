from django.conf import settings
from evennia.utils.optionclasses import BaseOption


class FactionPermissions(BaseOption):

    def validate(self, value, **kwargs):
        return self.handler.obj.validate_permissions(value)

    def default(self):
        return {v for val in self.default_value if (v := val.strip().lower())}

    def deserialize(self, save_data):
        return {v for val in save_data if (v := val.strip().lower())}

    def serialize(self):
        return self.value_storage

    def display(self, **kwargs):
        return " ".join(self.value)
