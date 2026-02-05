from django import forms


class CreatableModelChoiceField(forms.ModelChoiceField):
    def __init__(self, *args, create_key_name=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.create_key_name = create_key_name
        self.widget.attrs.update({"data-tomselect": "1", "data-tomselect:settings": '{"create": true}'})

    def to_python(self, value):
        if value in self.empty_values:
            return None
        try:
            key = self.to_field_name or "pk"
            if isinstance(value, self.queryset.model):
                value = getattr(value, key)
            value = self.queryset.get(**{key: value})
        except (ValueError, TypeError, self.queryset.model.DoesNotExist):
            create_key = self.create_key_name
            if create_key is None:
                raise forms.ValidationError(
                    self.error_messages["invalid_choice"],
                    code="invalid_choice",
                    params={"value": value},
                )
            value = self.queryset.create(**{create_key: value})
        return value
