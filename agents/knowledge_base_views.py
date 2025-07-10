# agents/knowledge_base_views.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class CreateKnowledgeBaseView(LoginRequiredMixin, TemplateView):
    """View for creating new KnowledgeBase objects"""
    template_name = 'agents/create_knowledge_base.html'
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Create KnowledgeBase'
        return context


class ManageKnowledgeBasesView(LoginRequiredMixin, TemplateView):
    """View for managing existing KnowledgeBase objects"""
    template_name = 'agents/manage_knowledge_bases.html'
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Manage Knowledge Bases'
        return context