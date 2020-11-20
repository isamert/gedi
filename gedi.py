import os
import tempfile
import subprocess
import jedi

from jedi.api import Script
from gi.repository import GObject, Gedit, Gtk, GtkSource, GLib
from threading import Thread, Event

# FIXME: find real icon names
icon_names = {
    'module':   'package-x-generic',
    'class':    'folder',
    'instance': 'edit-copy',
    'function': 'insert-object',
    'param':    'insert-link',
    'keyword':  'format-text-bold',
    'property': 'find-location',
    'statement': 'view-continuous',
}


class Jedi:
    def get_script(document):
        doc_text = document.get_text(
            document.get_start_iter(), document.get_end_iter(), False)
        iter_cursor = document.get_iter_at_mark(document.get_insert())
        linenum = iter_cursor.get_line() + 1
        charnum = iter_cursor.get_line_index()

        return Script(doc_text, linenum, charnum, document.get_uri_for_display())


class GediPlugin(GObject.Object, Gedit.ViewActivatable):
    __gtype_name__ = "GediPlugin"
    view = GObject.property(type=Gedit.View)

    def __init__(self):
        GObject.Object.__init__(self)
        self.completion_provider = None
        self.conn_id = None

    def do_activate(self):
        document = self.view.get_buffer()
        self.conn_id = document.connect("loaded", self.on_document_load)

    def do_deactivate(self):
        document = self.view.get_buffer()
        if self.conn_id:
            document.disconnect(self.conn_id)

    def on_document_load(self, document, p3=None, p4=None, p5=0, p6=0):
        hashbang_line = document.get_iter_at_line(
            0).get_text(document.get_iter_at_line(1))
        if document.props.mime_type == 'text/x-python' or (hashbang_line.startswith('#!/') and hashbang_line.find('python')):
            if self.completion_provider is None:
                self.completion_provider = GediCompletionProvider()
                self.view.get_completion().add_provider(self.completion_provider)
        else:
            if self.completion_provider is not None:
                self.view.get_completion().remove_provider(self.completion_provider)
                self.completion_provider = None


class JediPopulator(Thread):
    def __init__(self, provider, context):
        Thread.__init__(self)
        self._context = context
        self._provider = provider
        self._document = provider.get_iter_correctly(context).get_buffer()
        self._stop_request = Event()

    def run(self):
        proposals = []
        try:
            for completion in Jedi.get_script(self._document).completions():
                complete = completion.name
                if tuple(map(int,jedi.__version__.split('.'))) <= (0, 7, 0):
                    doc = completion.doc
                else:
                    doc = completion.docstring()

                comp = GtkSource.CompletionItem.new()
                comp.props.label = comp.props.text = completion.name
                comp.props.icon_name = icon_names.get(
                    completion.type.lower(), 'action-unavailable')
                comp.props.info = doc
                proposals.append(comp)
        except Exception:
            self.stop()

        if not self._stop_request.is_set():
            GLib.idle_add(self._context.add_proposals,
                          self._provider, proposals, True)

    def stop(self):
        self._stop_request.set()

    @property
    def stopped(self):
        return self._stop_request.is_set()


class GediCompletionProvider(GObject.Object, GtkSource.CompletionProvider):
    __gtype_name__ = 'GediProvider'

    def __init__(self):
        GObject.Object.__init__(self)
        self.thread = None

    def do_get_name(self):
        return _("Gedi Python Code Completion")

    def get_iter_correctly(self, context):
        if isinstance(context.get_iter(), tuple):
            return context.get_iter()[1]
        else:
            return context.get_iter()

    def do_match(self, context):
        iter = self.get_iter_correctly(context)
        iter.backward_char()
        buffer = iter.get_buffer()
        if buffer.get_context_classes_at_iter(iter) != ['no-spell-check']:
            return False
        ch = iter.get_char()
        if not (ch in ('_', '.') or ch.isalnum()):
            return False

        return True

    def do_get_priority(self):
        return 1

    def do_get_activation(self):
        return GtkSource.CompletionActivation.INTERACTIVE

    def do_populate(self, context):
        if self.thread and not self.thread.stopped:
            self.thread.stop()
        self.thread = JediPopulator(self, context)
        self.thread.start()


GObject.type_register(GediCompletionProvider)
