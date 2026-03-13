from django import forms
import bleach

from .models import Employee

class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ['first_name', 'last_name', 'department']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'shadow-sm focus:ring-indigo-500 focus:border-indigo-500 block w-full sm:text-sm border-gray-300 rounded-md', 'required': True, 'placeholder': 'First Name ... e.g. John'}),
            'last_name': forms.TextInput(attrs={'class': 'shadow-sm focus:ring-indigo-500 focus:border-indigo-500 block w-full sm:text-sm border-gray-300 rounded-md', 'required': True, 'placeholder': 'Last Name ... e.g. Doe'}),
            'department': forms.TextInput(attrs={'class': 'shadow-sm focus:ring-indigo-500 focus:border-indigo-500 block w-full sm:text-sm border-gray-300 rounded-md', 'required': True, 'placeholder': 'Department ... e.g. Sales'}),
        }

    def clean_first_name(self):
        data = self.cleaned_data['first_name']
        return bleach.clean(data, tags=[], attributes={}, strip=True).title()

    def clean_last_name(self):
        data = self.cleaned_data['last_name']
        return bleach.clean(data, tags=[], attributes={}, strip=True).title()

    def clean_department(self):
        data = self.cleaned_data['department']
        return bleach.clean(data, tags=[], attributes={}, strip=True).title()

    def clean(self):
        cleaned_data = super().clean()
        first_name = cleaned_data.get('first_name')
        last_name = cleaned_data.get('last_name')
        department = cleaned_data.get('department')

        if first_name and last_name:
            if Employee.objects.filter(first_name=first_name, last_name=last_name).exists():
                raise forms.ValidationError('Employee already exists.')

        return cleaned_data
