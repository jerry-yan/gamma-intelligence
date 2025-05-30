# accounts/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.generic import TemplateView
from .forms import CustomAuthenticationForm, UserProfileForm


def login_view(request):
    """Login-only view (registration removed)"""
    login_form = CustomAuthenticationForm()

    if request.method == 'POST':
        login_form = CustomAuthenticationForm(request, data=request.POST)
        if login_form.is_valid():
            username = login_form.cleaned_data.get('username')
            password = login_form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {username}!')
                next_url = request.GET.get('next', 'home')
                return redirect(next_url)
            else:
                messages.error(request, 'Invalid username or password.')

    context = {
        'login_form': login_form,
    }
    return render(request, 'accounts/login.html', context)


class HomeView(TemplateView):
    template_name = 'home.html'


@login_required
def account_view(request):
    """User account page with profile details"""
    user_profile = request.user.profile

    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=user_profile)
        if form.is_valid():
            # Update user fields
            request.user.username = form.cleaned_data['username']
            request.user.email = form.cleaned_data['email']
            request.user.save()

            # Save profile
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('account')
    else:
        form = UserProfileForm(instance=user_profile)

    context = {
        'form': form,
        'user_profile': user_profile,
    }
    return render(request, 'accounts/account.html', context)