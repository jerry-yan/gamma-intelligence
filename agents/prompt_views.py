from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import Prompt
from .forms import PromptForm


class PromptListView(LoginRequiredMixin, ListView):
    """List all prompts for the current user"""
    model = Prompt
    template_name = 'agents/prompts/list.html'
    context_object_name = 'prompts'
    paginate_by = 20

    def get_queryset(self):
        return Prompt.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['prompt_count'] = self.get_queryset().count()
        return context


class PromptCreateView(LoginRequiredMixin, CreateView):
    """Create a new prompt"""
    model = Prompt
    template_name = 'agents/prompts/form.html'
    form_class = PromptForm
    success_url = reverse_lazy('agents:prompt_list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f'Prompt "{form.instance.name}" created successfully!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Create'
        return context


class PromptUpdateView(LoginRequiredMixin, UpdateView):
    """Update an existing prompt"""
    model = Prompt
    template_name = 'agents/prompts/form.html'
    form_class = PromptForm
    success_url = reverse_lazy('agents:prompt_list')

    def get_queryset(self):
        return Prompt.objects.filter(user=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, f'Prompt "{form.instance.name}" updated successfully!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Edit'
        return context


@login_required
@csrf_exempt
@require_http_methods(["DELETE"])
def prompt_delete_view(request, pk):
    """Delete a prompt via AJAX"""
    try:
        prompt = get_object_or_404(Prompt, pk=pk, user=request.user)
        prompt_name = prompt.name
        prompt.delete()

        return JsonResponse({
            'success': True,
            'message': f'Prompt "{prompt_name}" deleted successfully!'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_http_methods(["GET"])
def prompt_detail_api(request, pk):
    """Get prompt details via AJAX"""
    try:
        prompt = get_object_or_404(Prompt, pk=pk, user=request.user)

        return JsonResponse({
            'success': True,
            'prompt': {
                'id': prompt.id,
                'name': prompt.name,
                'prompt': prompt.prompt,
                'created_at': prompt.created_at.isoformat(),
                'updated_at': prompt.updated_at.isoformat()
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)