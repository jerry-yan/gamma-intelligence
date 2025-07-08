from django import forms

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