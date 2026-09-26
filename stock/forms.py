from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Member, Room, StockItem, Block, SystemItem


class LoginForm(forms.Form):
    username = forms.CharField(
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Username", "autofocus": True})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "input", "placeholder": "Password"})
    )


class RegistrationForm(UserCreationForm):
    full_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"class": "input"}))
    contact_number = forms.CharField(
        max_length=20, required=False, widget=forms.TextInput(attrs={"class": "input"})
    )
    role = forms.ChoiceField(choices=Member.ROLE_CHOICES, widget=forms.Select(attrs={"class": "input"}))

    class Meta:
        model = Member
        fields = ["full_name", "username", "contact_number", "role", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({"class": "input"})
        self.fields["password1"].widget.attrs.update({"class": "input"})
        self.fields["password2"].widget.attrs.update({"class": "input"})

    def clean_username(self):
        username = self.cleaned_data["username"]
        if Member.objects.filter(username__iexact=username).exists():
            raise ValidationError("This username is already taken. Please choose another.")
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        user.full_name = self.cleaned_data["full_name"]
        user.contact_number = self.cleaned_data.get("contact_number", "")
        user.role = self.cleaned_data["role"]
        if commit:
            user.save()
        return user


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ["room_no", "room_name", "room_id", "auto_update_db"]
        widgets = {
            "room_no": forms.TextInput(attrs={"class": "input", "readonly": "readonly"}),
            "room_name": forms.TextInput(attrs={"class": "input", "placeholder": "Room Name"}),
            "room_id": forms.TextInput(attrs={"class": "input", "placeholder": "Room ID (optional)"}),
            "auto_update_db": forms.CheckboxInput(attrs={"class": "checkbox"}),
        }


class StockItemForm(forms.ModelForm):
    item_name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            "class": "input cell-input master-name", "placeholder": "Select Item Name",
            "list": "system-item-list", "autocomplete": "off", "data-code-target": "id_item_code",
        }),
    )
    item_code = forms.CharField(
        max_length=100, required=False,
        widget=forms.TextInput(attrs={
            "class": "input cell-input master-code", "placeholder": "Generated automatically", "readonly": "readonly",
        }),
    )

    class Meta:
        model = StockItem
        fields = ["item_name", "item_code", "item_no", "quantity", "status", "last_updated"]
        widgets = {
            "item_no": forms.TextInput(attrs={"class": "input cell-input", "placeholder": "Auto", "readonly": "readonly"}),
            "quantity": forms.NumberInput(attrs={"class": "input cell-input", "min": 0}),
            "status": forms.Select(attrs={"class": "input cell-input"}),
            "last_updated": forms.DateTimeInput(
                attrs={"class": "input cell-input", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["last_updated"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"]
        self.fields["item_no"].required = False
        self.system_items = list(SystemItem.objects.order_by("item_name", "item_code"))
        if self.instance and self.instance.pk and self.instance.item_id:
            self.initial["item_name"] = self.instance.item.item_name
            self.initial["item_code"] = self.instance.item.item_code
        elif self.instance and self.instance.pk:
            self.initial["item_name"] = self.instance.item_name
            self.initial["item_code"] = self.instance.item_code
        if self.instance and self.instance.pk and self.instance.last_updated:
            self.initial["last_updated"] = timezone.localtime(self.instance.last_updated).strftime("%Y-%m-%dT%H:%M")

    def clean_item_name(self):
        name = self.cleaned_data["item_name"].strip()
        if not name:
            raise ValidationError("Item Name is required.")
        item = SystemItem.objects.filter(item_name__iexact=name).first()
        if not item:
            raise ValidationError("Select an Item Name from System Control.")
        self._system_item = item
        return item.item_name

    def clean_item_code(self):
        # The browser displays Item Code, but the backend never trusts a
        # posted/manual code. The selected Item Name resolves the SystemItem;
        # views regenerate the complete location-based code on save.
        item = getattr(self, "_system_item", None)
        return item.item_code if item else ""

    def clean_quantity(self):
        qty = self.cleaned_data["quantity"]
        if qty < 0:
            raise ValidationError("Quantity cannot be negative.")
        return qty

    def save(self, commit=True):
        obj = super().save(commit=False)
        item = getattr(self, "_system_item", None)
        if not item:
            item = SystemItem.objects.get(item_code=self.cleaned_data["item_code"])
        obj.item = item
        obj.item_name = item.item_name
        obj.item_code = item.item_code
        if commit:
            obj.save()
        return obj


class StockSearchForm(forms.Form):
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Search item name, code, no. or room"}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All Status"), (StockItem.STATUS_ALIVE, "ALIVE"), (StockItem.STATUS_REPAIR, "REPAIR"), (StockItem.STATUS_DEAD, "DEAD")],
        widget=forms.Select(attrs={"class": "input"}),
    )


class ReportFilterForm(forms.Form):
    ALL_BLOCKS = "ALL"
    ALL_STATUS = "ALL"

    block = forms.ChoiceField(
        choices=[(ALL_BLOCKS, "All Blocks")] + Block.SOURCE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "input"}),
    )
    status = forms.ChoiceField(
        choices=[(ALL_STATUS, "All"), (StockItem.STATUS_ALIVE, "ALIVE"), (StockItem.STATUS_REPAIR, "REPAIR"), (StockItem.STATUS_DEAD, "DEAD")],
        required=False,
        widget=forms.Select(attrs={"class": "input"}),
    )
    item_code = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": "input",
            "placeholder": "Search by Item Code",
            "autocomplete": "off",
        }),
    )


class AnalysisFilterForm(forms.Form):
    """Filter bar for the ANALYSIS page: block, floor, room, status and a
    free-text search.

    The Room dropdown is deliberately NOT a Django field here — it's built
    directly in the template from a live Room queryset so the page can
    filter it client-side with a few lines of JS as soon as a Block and/or
    Floor is chosen, without an extra round-trip.
    """
    ALL_BLOCKS = "ALL"
    ALL_FLOORS = "ALL"
    ALL_STATUS = "ALL"

    block = forms.ChoiceField(
        choices=[(ALL_BLOCKS, "All Blocks")] + Block.SOURCE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "input", "id": "id_block_filter"}),
    )
    floor = forms.ChoiceField(
        choices=[(ALL_FLOORS, "All Floors")] + Room.FLOOR_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "input", "id": "id_floor_filter"}),
    )
    status = forms.ChoiceField(
        choices=[(ALL_STATUS, "All"), (StockItem.STATUS_ALIVE, "ALIVE"), (StockItem.STATUS_REPAIR, "REPAIR"), (StockItem.STATUS_DEAD, "DEAD")],
        required=False,
        widget=forms.Select(attrs={"class": "input"}),
    )
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Search item name, code or item no."}),
    )


class DeadStockFilterForm(forms.Form):
    ALL_BLOCKS = "ALL"
    source_table = forms.ChoiceField(
        choices=[(ALL_BLOCKS, "All Source Tables")] + Block.SOURCE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "input"}),
    )
    item_code = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": "input",
            "placeholder": "Search by Item Code",
            "autocomplete": "off",
        }),
    )
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Search dead stock"}),
    )


class ImportFileForm(forms.Form):
    file = forms.FileField(widget=forms.ClearableFileInput(attrs={"class": "input"}))

    def clean_file(self):
        f = self.cleaned_data["file"]
        name = f.name.lower()
        if not (name.endswith(".csv") or name.endswith(".xlsx") or name.endswith(".xls")):
            raise ValidationError("Only .csv, .xlsx or .xls files are supported.")
        if f.size > 5 * 1024 * 1024:
            raise ValidationError("File is too large (max 5 MB).")
        return f
