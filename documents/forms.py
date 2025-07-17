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

    # Knowledge Base selection dropdown
    knowledge_base = forms.ModelChoiceField(
        queryset=KnowledgeBase.objects.filter(is_active=True),
        label='Knowledge Base',
        required=False,  # Made optional
        empty_label='-- None (No Knowledge Base) --',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Select the knowledge base for this document (optional)'
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

    expiration_rule = forms.ChoiceField(
        label='Expiration Rule',
        required=True,  # MANDATORY
        choices=[
            ('evergreen', 'Evergreen'),
            ('standard', 'Standard'),
        ],
        widget=forms.RadioSelect(attrs={
            'class': 'form-check-input',
            'id': 'expiration-rule'
        }),
        help_text='Select whether this document should be persistent (Evergreen) or temporary (Standard)'
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
            'report_type',
        ]
        widgets = {
            'publication_date': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'form-control',
                    'required': True  # Make it required in HTML
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make publication_date field required
        self.fields['publication_date'].required = True
        self.fields['publication_date'].help_text = 'Publication date is required'

        # Customize knowledge base display to show display_name
        self.fields['knowledge_base'].label_from_instance = lambda obj: obj.display_name

    def clean_publication_date(self):
        """Ensure publication date is provided"""
        publication_date = self.cleaned_data.get('publication_date')
        if not publication_date:
            raise ValidationError('Publication date is required.')
        return publication_date

    def clean_expiration_rule(self):
        """Ensure expiration rule is selected"""
        expiration_rule = self.cleaned_data.get('expiration_rule')
        if not expiration_rule:
            raise ValidationError('You must select an expiration rule (Evergreen or Standard).')
        return expiration_rule

    def clean(self):
        """Additional form validation"""
        cleaned_data = super().clean()

        # Handle report type logic
        report_type_choice = cleaned_data.get('report_type_choice')
        custom_report_type = cleaned_data.get('custom_report_type')

        if report_type_choice == 'custom':
            if not custom_report_type:
                raise ValidationError({
                    'custom_report_type': 'Please enter a custom report type.'
                })
            cleaned_data['report_type'] = custom_report_type
        elif report_type_choice:
            cleaned_data['report_type'] = report_type_choice
        else:
            cleaned_data['report_type'] = 'general'

        # Handle metadata
        metadata_json = cleaned_data.get('metadata_json', '')
        if metadata_json:
            try:
                metadata = json.loads(metadata_json)
                cleaned_data['metadata'] = metadata
            except json.JSONDecodeError:
                cleaned_data['metadata'] = {}
        else:
            cleaned_data['metadata'] = {}

        return cleaned_data

    def save(self, commit=True):
        """Save the document with the expiration rule converted to is_persistent_document"""
        document = super().save(commit=False)

        # Convert expiration_rule to is_persistent_document boolean
        expiration_rule = self.cleaned_data.get('expiration_rule')
        document.is_persistent_document = (expiration_rule == 'evergreen')

        # Set vector_group_id from selected knowledge_base
        knowledge_base = self.cleaned_data.get('knowledge_base')
        if knowledge_base:
            document.vector_group_id = knowledge_base.vector_group_id

        # Set report_type (determined in clean() method)
        document.report_type = self.cleaned_data.get('report_type', 'general')

        # Set metadata
        document.metadata = self.cleaned_data.get('metadata', {})

        if commit:
            document.save()
        return document