# agents/knowledge_base_views.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from .models import KnowledgeBase, StockTicker
from documents.models import Document
from research_summaries.models import ResearchNote


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


class KnowledgeBaseMetricsView(LoginRequiredMixin, TemplateView):
    """View for displaying metrics of documents in each KnowledgeBase"""
    template_name = 'agents/knowledge_base_metrics.html'
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Knowledge Base Metrics'

        # Get all active knowledge bases sorted by vector_group_id
        knowledge_bases = KnowledgeBase.objects.filter(
            is_active=True
        ).order_by('vector_group_id')

        kb_data_list = []

        for kb in knowledge_bases:
            kb_data = {
                'kb': kb,
                'documents': [],
                'research_notes': [],
                'total_count': 0
            }

            # Get Documents for this KnowledgeBase
            documents = Document.objects.filter(
                is_vectorized=True,
                vector_group_id=kb.vector_group_id
            ).order_by('filename')

            kb_data['documents'] = list(documents)

            # Get ResearchNotes - this is more complex
            # First, get notes that directly have this vector_group_id
            direct_notes = ResearchNote.objects.filter(
                is_vectorized=True,
                vector_group_id=kb.vector_group_id
            )

            # Second, get notes that should be in this KB based on ticker mapping
            # Find all tickers that map to this vector_group_id
            tickers_for_kb = StockTicker.objects.filter(
                vector_id=kb.vector_group_id
            ).values_list('main_ticker', flat=True)

            # Find notes with these tickers
            ticker_based_notes = ResearchNote.objects.filter(
                is_vectorized=True,
                parsed_ticker__in=tickers_for_kb
            )

            # Combine both sets of notes (use union to avoid duplicates)
            all_notes = direct_notes.union(ticker_based_notes).order_by('raw_title')

            kb_data['research_notes'] = list(all_notes)
            kb_data['total_count'] = len(kb_data['documents']) + len(kb_data['research_notes'])

            kb_data_list.append(kb_data)

        context['knowledge_bases'] = kb_data_list

        return context