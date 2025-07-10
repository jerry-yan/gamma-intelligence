# documents/forms.py
from django import forms
from django.core.exceptions import ValidationError
from .models import Document
import json


class DocumentUploadForm(forms.ModelForm):
    file = forms.FileField(
        label='Select File',
        help_text='Upload a PDF or other document file',
        widget=forms.FileInput(attrs={'accept': '.pdf,.doc,.docx,.txt,.xlsx,.xls'})
    )

    # Custom report type field that allows dropdown or custom input
    report_type_choice = forms.ChoiceField(
        label='Report Type',
        required=False,
        choices=[
            ('', '-- Select or enter custom --'),
            ('Company Update', 'Company Update'),
            ('Quarter Preview', 'Quarter Preview'),
            ('Initiation Report', 'Initiation Report'),
            ('general', 'General Document'),
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

    # Metadata fields (will be handled by JavaScript)
    metadata_json = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )

    class Meta:
        model = Document
        fields = [
            'file_directory',
            'vector_group_id',
            'publication_date',
        ]
        widgets = {
            'vector_group_id': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'min': '1',
                    'placeholder': 'Enter vector group ID (required)'
                }
            ),
            'publication_date': forms.DateInput(
                attrs={
                    'class': 'form-control',
                    'type': 'date'
                }
            ),
        }
        labels = {
            'vector_group_id': 'Vector Group ID',
            'publication_date': 'Publication Date (Optional)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make vector_group_id required
        self.fields['vector_group_id'].required = True
        self.fields['vector_group_id'].error_messages = {
            'required': 'Vector Group ID is required'
        }

    def clean(self):
        cleaned_data = super().clean()
        report_type_choice = cleaned_data.get('report_type_choice')
        custom_report_type = cleaned_data.get('custom_report_type')

        # Determine final report type
        if report_type_choice == 'custom':
            if not custom_report_type:
                raise ValidationError('Please enter a custom report type')
            cleaned_data['report_type'] = custom_report_type
        elif report_type_choice:
            cleaned_data['report_type'] = report_type_choice
        else:
            cleaned_data['report_type'] = 'general'

        # Parse metadata JSON
        metadata_json = cleaned_data.get('metadata_json', '{}')
        try:
            metadata = json.loads(metadata_json) if metadata_json else {}
            # Validate metadata
            if len(metadata) > 16:
                raise ValidationError('Maximum 16 metadata key-value pairs allowed')
            cleaned_data['metadata'] = metadata
        except json.JSONDecodeError:
            raise ValidationError('Invalid metadata format')

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Set the report type from cleaned data
        instance.report_type = self.cleaned_data.get('report_type', 'general')
        # Set metadata
        instance.metadata = self.cleaned_data.get('metadata', {})
        if commit:
            instance.save()
        return instance