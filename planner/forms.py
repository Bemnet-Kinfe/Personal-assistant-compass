from django import forms

from .models import COLOR_CHOICES, Area, Task


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "area", "due_date", "minutes", "priority", "energy", "notes"]
        labels = {"title": "What needs doing", "due_date": "Due", "minutes": "Time it takes (minutes)"}
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Grade problem set 4", "autofocus": True}),
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "minutes": forms.NumberInput(attrs={"min": 5, "max": 720, "step": 5}),
            "priority": forms.RadioSelect,
            "energy": forms.RadioSelect,
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, user, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
        self.fields["area"].queryset = Area.objects.filter(user=user)
        self.fields["area"].empty_label = None
        self.fields["minutes"].min_value = 5
        self.fields["minutes"].max_value = 720


class AreaForm(forms.ModelForm):
    class Meta:
        model = Area
        fields = ["name", "color", "is_personal"]
        labels = {"is_personal": "Counts as personal time"}

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["color"].choices = COLOR_CHOICES

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        clash = Area.objects.filter(user=self.user, name__iexact=name).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("You already have an area with that name.")
        return name


