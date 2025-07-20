# documents/forms.py
from django import forms
from django.core.exceptions import ValidationError
from .models import Document
from agents.models import KnowledgeBase
import json


class DocumentUploadForm(forms.ModelForm):
    file = forms.FileField(
        label='Select File',
        help_text='Upload a PDF or other document file',
        widget=forms.FileInput(attrs={'accept': '.pdf,.doc,.docx,.txt,.xlsx,.xls'})
    )

    # Multiple Knowledge Base selection with checkboxes
    knowledge_bases = forms.ModelMultipleChoiceField(
        queryset=KnowledgeBase.objects.filter(is_active=True),
        label='Knowledge Bases',
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        help_text='Select one or more knowledge bases for this document (optional)'
    )

    # Custom report type field that allows dropdown or custom input
    report_type_choice = forms.ChoiceField(
        label='Report Type',
        required=False,
        choices=[
            ('', '-- Select or enter custom --'),
            ('Company Update', 'Company Update'),
            ('Company Filing', 'Company Filing'),
            ('Quarter Review', 'Quarter Review'),
            ('Quarter Preview', 'Quarter Preview'),
            ('Initiation Report', 'Initiation Report'),
            ('Industry Note', 'Industry Note'),
            ('custom', 'Custom (enter below)'),
        ],
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'report-type-select'})
    )

    custom_report_type = forms.CharField(
        label='Custom Report Type',
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter custom report type',
            'id': 'custom-report-type'
        })
    )

    expiration_rules = forms.ChoiceField(
        label='Expiration Rules',
        required=True,
        choices=[
            ('evergreen', 'Evergreen'),
            ('standard', 'Standard'),
        ],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        initial='standard',
    )

    # Metadata fields (will be handled by JavaScript)
    metadata_json = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )

    class Meta:
        model = Document
        fields = [
            'publication_date',
        ]
        widgets = {
            'publication_date': forms.DateInput(
                attrs={
                    'class': 'form-control',
                    'type': 'date',
                    'required': True
                }
            ),
        }
        labels = {
            'publication_date': 'Publication Date',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Customize the display of knowledge bases in the checkboxes
        self.fields['knowledge_bases'].label_from_instance = lambda obj: obj.display_name
        self.fields['publication_date'].required = True

    def clean(self):
        cleaned_data = super().clean()
        report_type_choice = cleaned_data.get('report_type_choice')
        custom_report_type = cleaned_data.get('custom_report_type')

        # If 'custom' is selected, ensure custom_report_type is provided
        if report_type_choice == 'custom' and not custom_report_type:
            raise ValidationError({
                'custom_report_type': 'Please enter a custom report type.'
            })

        # Parse metadata JSON
        metadata_json = cleaned_data.get('metadata_json', '{}')
        try:
            metadata = json.loads(metadata_json)
            cleaned_data['metadata'] = metadata
        except json.JSONDecodeError:
            cleaned_data['metadata'] = {}

        return cleaned_data

    def get_report_type(self):
        """Helper method to get the final report type"""
        report_type_choice = self.cleaned_data.get('report_type_choice')
        custom_report_type = self.cleaned_data.get('custom_report_type')

        if report_type_choice == 'custom':
            return custom_report_type
        elif report_type_choice:
            return report_type_choice
        else:
            return 'general'

    def get_expiration_rules(self):
        """Helper method to get if document is persistent"""
        expiration_rules = self.cleaned_data.get('expiration_rules')
        return expiration_rules == 'evergreen'