from django import forms
from .models import Prompt


class ExcelUploadForm(forms.Form):
    excel_file = forms.FileField(
        label='Select Excel File',
        help_text='Upload .xls or .xlsx file with stock ticker data',
        widget=forms.FileInput(attrs={'accept': '.xls,.xlsx'})
    )
    clear_existing = forms.BooleanField(
        label='Clear existing data before import',
        required=False,
        initial=False,
        help_text='Check this to remove all existing stock tickers before importing'
    )


class PromptForm(forms.ModelForm):
    """Form for creating and editing prompts"""

    class Meta:
        model = Prompt
        fields = ['name', 'prompt']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter a descriptive name for your prompt',
                'maxlength': '200'
            }),
            'prompt': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your prompt here...',
                'rows': 8,
                'style': 'resize: vertical;'
            })
        }
        labels = {
            'name': 'Prompt Name',
            'prompt': 'Prompt Content'
        }
        help_texts = {
            'name': 'Give your prompt a unique, descriptive name',
            'prompt': 'You can write multiple paragraphs. This prompt can be used in your chat sessions.'
        }

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name:
            # Check if user already has a prompt with this name (excluding current instance if editing)
            user = self.instance.user if self.instance.pk else None
            existing = Prompt.objects.filter(user=user, name=name)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError('You already have a prompt with this name.')
        return name