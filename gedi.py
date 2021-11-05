#!/usr/bin/env python3

import jedi, os.path, threading
from gi.repository import Gtk, GLib, Gedit, GObject, GdkPixbuf, GtkSource

# TODO: add settings menu
jedi.settings.fast_parser = False  # thread-safety
jedi.settings.case_insensitive_completion = False  # case-sensitive
jedi.settings.add_bracket_after_function = True  # convenience

ICON_NAMES = {
	'module': 'xapp-prefs-plugins-symbolic',
	'class': 'application-x-appliance-symbolic',
	'instance': 'insert-object-symbolic',
	'function': 'system-run-symbolic',
	'param': 'dialog-question-symbolic',
	'path': 'inode-directory-symbolic',
	'keyword': 'insert-text-symbolic',
	'property': 'document-properties-symbolic',
	'statement': 'document-send-symbolic',
}

class GediPlugin(GObject.Object, Gedit.ViewActivatable):
	view = GObject.property(type=Gedit.View)

	def __init__(self):
		super().__init__()
		self.completion_provider = None
		self.signal = None

	def do_activate(self):
		document = self.view.get_buffer()
		self.signal = document.connect('loaded', self.on_document_load)
		self.on_document_load(document)

	def do_deactivate(self):
		if (self.signal is not None):
			document = self.view.get_buffer()
			document.disconnect(self.signal)
			self.signal = None

	def on_document_load(self, document, *_):
		if ((lang := document.get_language()) and 'python' in lang.get_name().casefold()):
			self.completion_provider = GediCompletionProvider(document)
			self.view.get_completion().add_provider(self.completion_provider)
		else:
			if (self.completion_provider is not None):
				self.view.get_completion().remove_provider(self.completion_provider)
				self.completion_provider = None

class GediCompletionProvider(GObject.Object, GtkSource.CompletionProvider):
	name = "Code completion"
	priority = 1

	def __init__(self, document):
		super().__init__()
		self.document = document
		self.icon = GdkPixbuf.Pixbuf.new_from_file_at_scale(os.path.join(os.path.dirname(__file__), 'logo.png'), 16, 16, True)
		self.populate_thread_ident = None
		self.populate_thread_lock = threading.Lock()

	def do_get_activation(self):
		return GtkSource.CompletionActivation.INTERACTIVE

	def do_get_icon(self):
		return self.icon

	def do_get_info_widget(self, proposal):
		buffer = GtkSource.Buffer(
			highlight_matching_brackets = False,
			language = self.document.get_language(),
			style_scheme = self.document.get_style_scheme(),
		)

		widget = GtkSource.View(
			buffer = buffer,
			can_focus = False,
			cursor_visible = False,
			editable = False,
			highlight_current_line = False,
			sensitive = False,
		)

		widget.show()

		return widget

	def do_get_name(self):
		return _(self.name)

	def do_get_priority(self):
		return self.priority

	def do_match(self, context):
		iter = context.get_iter()[1]
		iter.backward_char()
		if ('no-spell-check' not in self.document.get_context_classes_at_iter(iter)): return False
		ch = iter.get_char()
		return (ch in '_.' or ch.isalnum())

	def do_populate(self, context):
		# do our best to prevent previous thread to call `idle_add()`
		self.populate_thread_ident = None
		with self.populate_thread_lock:
			self.populate_thread_ident = None

		code = self.document.get_text(self.document.get_start_iter(), self.document.get_end_iter(), False)
		path = (loc.get_path() if (loc := self.document.get_file().get_location()) else '')
		iter_cursor = self.document.get_iter_at_mark(self.document.get_insert())
		linenum = iter_cursor.get_line()+1
		charnum = iter_cursor.get_line_index()

		with self.populate_thread_lock:
			t = threading.Thread(target=self.populate, args=(context, code, path, linenum, charnum), daemon=True)
			t.start()
			self.populate_thread_ident = t.ident

	def do_update_info(self, proposal, info):
		widget = info.get_child()
		buffer = widget.get_buffer()
		buffer.set_text(proposal.get_info())

	def populate(self, context, code: str, path: str, linenum: int, charnum: int):
		script = jedi.Script(code=code, path=path, environment=jedi.api.environment.InterpreterEnvironment())
		completions = script.complete(linenum, charnum, fuzzy=False)  # TODO: add setting for `fuzzy`

		proposals = [GtkSource.CompletionItem(
		             	label = i.name,
		             	text = i.name_with_symbols,
		             	icon_name = ICON_NAMES.get(i.type.casefold(), Gtk.STOCK_ADD),
		             	info = i.docstring(),
		             ) for i in completions]

		ident = threading.get_ident()
		with self.populate_thread_lock:
			if (ident == self.populate_thread_ident):
				GLib.idle_add(context.add_proposals, self, proposals, True)
