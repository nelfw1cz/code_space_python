"""
PyEdit — редактор Python-кода на tkinter/ttk в тёмной теме (Darcula-like).

Возможности:
  • Проводник файлов текущей директории (ленивая подгрузка папок)
  • Панель быстрой вставки заготовок кода в позицию курсора
  • Подсветка синтаксиса (ключевые слова, строки, комментарии, числа и др.)
  • Умные автоотступы (после «:» добавляется 4 пробела)
  • Запуск кода в фоновом процессе, вывод в реальном времени в консоль
  • Отступ/сдвиг блока по Tab / Shift+Tab, Ctrl+S/O/N, F5 — запуск

Запуск:  python pyedit.py
"""

from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from functools import partial
from tkinter import font as tkfont
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# ============================================================
# 1. ПАЛИТРА И КОНСТАНТЫ
# ============================================================

COLORS = {
    # Общая схема
    'bg':       '#1E1F22',   # фон редактора
    'bg2':      '#191A1C',   # фон консоли (чуть темнее)
    'panel':    '#2B2D30',   # панели, тулбар, сайдбар
    'panel2':   '#26282E',   # статусбар
    'border':   '#393B40',   # разделители и саше
    'text':     '#BCC3CD',   # основной текст
    'text_dim': '#7A7E85',   # приглушённый текст
    'caret':    '#E8E8E8',   # курсор-каретка
    'select':   '#264F78',   # выделение
    'tree_bg':  '#26282E',   # фон проводника

    # Кнопки
    'btn':          '#43464B',
    'btn_hover':    '#50545B',
    'btn_press':    '#383B40',
    'btn_fg':       '#D3D5D9',
    'btn_disabled': '#313338',

    # Акцентные кнопки
    'run':        '#2F7E52', 'run_hover':  '#37925F', 'run_press':  '#297049',
    'stop':       '#8C4141', 'stop_hover': '#A34C4C', 'stop_press': '#7A3838',

    # Прокрутка / проводник
    'scroll':       '#4A4E54', 'scroll_hover': '#5A5F66',
    'dir':          '#C9A86A',

    # Синтаксис
    'kw':      '#CC7832',   # ключевые слова
    'string':  '#7AA85C',   # строки
    'comment': '#7A7E85',   # комментарии
    'number':  '#6897BA',   # числа
    'func':    '#E8C07E',   # имена функций/классов
    'builtin': '#82AAFF',   # встроенные функции
    'selfkw':  '#C586C0',   # self / cls
    'decor':   '#C0A85C',   # декораторы

    # Консоль
    'err': '#F07178',
    'ok':  '#6FBF73',
}

KEYWORDS = [
    'False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await',
    'break', 'case', 'class', 'continue', 'def', 'del', 'elif', 'else',
    'except', 'finally', 'for', 'from', 'global', 'if', 'import', 'in',
    'is', 'lambda', 'match', 'nonlocal', 'not', 'or', 'pass', 'raise',
    'return', 'try', 'while', 'with', 'yield',
]

BUILTINS = [
    'print', 'len', 'range', 'enumerate', 'zip', 'map', 'filter', 'sorted',
    'reversed', 'sum', 'min', 'max', 'abs', 'round', 'int', 'float', 'str',
    'bool', 'list', 'dict', 'set', 'tuple', 'input', 'open', 'type',
    'isinstance', 'issubclass', 'super', 'id', 'hash', 'repr', 'format',
    'vars', 'dir', 'getattr', 'setattr', 'hasattr', 'callable', 'iter',
    'next', 'Exception', 'ValueError', 'TypeError', 'KeyError',
    'IndexError', 'OSError', 'RuntimeError', 'StopIteration',
    '__init__', '__name__', '__main__', '__str__', '__repr__', '__doc__',
]

# (Подпись кнопки, шаблон кода, фрагмент, который будет выделен после вставки)
SNIPPETS = [
    ('Цикл for',   'for i in range(10):\n    print(i)\n',                       'range(10)'),
    ('Цикл while', 'while True:\n    ',                                          'True'),
    ('Условие if', 'if condition:\n    ',                                        'condition'),
    ('if / else',  'if condition:\n    pass\nelse:\n    pass\n',                 'condition'),
    ('Функция',    'def function_name():\n    return None\n',                    'function_name'),
    ('print()',    'print("Привет, мир!")\n',                                    '"Привет, мир!"'),
    ('try/except', 'try:\n    pass\nexcept Exception as e:\n    print(e)\n',     'Exception'),
    ('Класс',      'class MyClass:\n    def __init__(self):\n        pass\n',    'MyClass'),
]

# Папки, которые не показываются в проводнике
HIDDEN = {
    '.git', '__pycache__', '.idea', '.vscode', '.venv', 'venv', 'env',
    'node_modules', '.mypy_cache', '.pytest_cache', 'dist', 'build',
}

MONO_FAMILIES = (
    'JetBrains Mono', 'Cascadia Code', 'Cascadia Mono', 'Fira Code',
    'Consolas', 'SF Mono', 'Menlo', 'Ubuntu Mono', 'DejaVu Sans Mono',
    'Courier New',
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) or os.getcwd()

# Стартовый пример кода в редакторе
DEMO_CODE = '''\
# Добро пожаловать в PyEdit!
# Нажмите F5 или кнопку «Запустить», чтобы выполнить этот код.

def fib(n):
    """Возвращает первые n чисел Фибоначчи."""
    a, b = 0, 1
    result = []
    while len(result) < n:
        result.append(a)
        a, b = b, a + b
    return result


if __name__ == "__main__":
    for i, x in enumerate(fib(10), start=1):
        print(f"{i:2d}. {x}")
'''

# ============================================================
# 2. РЕГУЛЯРНЫЕ ВЫРАЖЕНИЯ ДЛЯ ПОДСВЕТКИ СИНТАКСИСА
# ============================================================
# Порядок ветвей = приоритет: сначала строки и комментарии, затем
# имена после def/class, ключевые слова, встроенные функции, числа.

_STR_PREFIX = r'(?:[rRbBfFuU]{1,2})?'
_RE_STRING = (
    r'(?P<string>' + _STR_PREFIX + r'(?:'
    r'"""(?:\\.|[^\\])*?(?:"""|$)'          # тройные двойные (в т.ч. незакрытые)
    r"|'''(?:\\.|[^\\])*?(?:'''|$)"         # тройные одинарные
    r'|"(?:\\.|[^"\\\n])*"?'                # обычные двойные (до конца строки)
    r"|'(?:\\.|[^'\\\n])*'?"                # обычные одинарные
    r'))'
)
_RE_COMMENT = r'(?P<comment>#[^\n]*)'
_RE_DECOR   = r'(?P<decorator>@[A-Za-z_][\w.]*)'
_RE_FUNC    = r'(?P<funcname>(?:(?<=\bdef\s)|(?<=\bclass\s))[A-Za-z_]\w*)'
_RE_KEYWORD = r'(?P<keyword>\b(?:' + '|'.join(KEYWORDS) + r')\b)'
_RE_SELF    = r'(?P<selfkw>\b(?:self|cls)\b)'
_RE_BUILTIN = r'(?P<builtin>\b(?:' + '|'.join(BUILTINS) + r')\b)'
_RE_NUMBER  = (
    r'(?P<number>\b(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|'
    r'\d[\d_]*(?:\.[\d_]+)?(?:[eE][+-]?\d+)?)\b)'
)

HIGHLIGHT_RE = re.compile('|'.join([
    _RE_STRING, _RE_COMMENT, _RE_DECOR, _RE_FUNC,
    _RE_KEYWORD, _RE_SELF, _RE_BUILTIN, _RE_NUMBER,
]))
HIGHLIGHT_TAGS = ('string', 'comment', 'decorator', 'funcname',
                  'keyword', 'selfkw', 'builtin', 'number')


def _enable_dpi() -> None:
    """Чёткий рендеринг на дисплеях с высоким DPI (Windows)."""
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


# ============================================================
# 3. ГЛАВНЫЙ КЛАСС ПРИЛОЖЕНИЯ
# ============================================================

class PyEdit(tk.Tk):
    """Основное окно редактора."""

    # ------------------------- инициализация -------------------------

    def __init__(self) -> None:
        super().__init__()
        self.title('PyEdit — редактор Python')
        self.geometry('1000x700')
        self.minsize(860, 560)
        self.configure(bg=COLORS['panel'])

        # Состояние
        self.current_path: str | None = None   # открытый файл
        self.modified: bool = False            # есть несохранённые изменения
        self.process: subprocess.Popen | None = None
        self._readers: list[threading.Thread] = []
        self.output_queue: queue.Queue = queue.Queue()
        self._temp_path: str | None = None
        self._run_start: float = 0.0
        self._hl_after: str | None = None      # id отложенной подсветки
        self._sashes_done = False

        self._setup_fonts()
        self._setup_style()
        self._build_menu()
        self._build_toolbar()
        self._build_main()
        self._build_statusbar()
        self._bind_events()

        # Стартовое содержимое
        self._set_editor_text(DEMO_CODE)
        self._after_file_changed()
        self._console_write(
            'info',
            'Консоль готова. Запуск кода — кнопка «Запустить» или F5.\n'
            'Примечание: input() при встроенном запуске не поддерживается.\n',
        )
        self._poll_output()
        self.protocol('WM_DELETE_WINDOW', self._on_close)
        self.editor.focus_set()

    # ------------------------- шрифты и стили -------------------------

    def _setup_fonts(self) -> None:
        families = set(tkfont.families(self))
        mono = next((f for f in MONO_FAMILIES if f in families),
                    tkfont.nametofont('TkFixedFont').actual('family'))
        self.mono_font   = tkfont.Font(family=mono, size=11)
        self.mono_bold   = tkfont.Font(family=mono, size=11, weight='bold')
        self.mono_italic = tkfont.Font(family=mono, size=11, slant='italic')
        self.console_font   = tkfont.Font(family=mono, size=10)
        self.console_italic = tkfont.Font(family=mono, size=10, slant='italic')

        if sys.platform == 'win32':
            ui = 'Segoe UI'
        elif sys.platform == 'darwin':
            ui = 'SF Pro Text'
        else:
            ui = 'DejaVu Sans'
        if ui not in families:
            ui = tkfont.nametofont('TkDefaultFont').actual('family')
        self.ui_font  = tkfont.Font(family=ui, size=10)
        self.ui_bold  = tkfont.Font(family=ui, size=10, weight='bold')
        self.ui_small = tkfont.Font(family=ui, size=9, weight='bold')

    def _btn_style(self, st: ttk.Style, name: str, bg: str, hover: str,
                   press: str, fg: str, pad: tuple[int, int]) -> None:
        st.configure(name, background=bg, foreground=fg, borderwidth=0,
                     relief='flat', focuscolor=bg, focusthickness=0,
                     padding=pad, font=self.ui_font)
        st.map(name,
               background=[('active', hover), ('pressed', press),
                           ('disabled', COLORS['btn_disabled'])],
               foreground=[('disabled', '#6C7076')],
               relief=[('active', 'flat'), ('pressed', 'flat')])

    def _setup_style(self) -> None:
        C = COLORS
        st = ttk.Style(self)
        st.theme_use('clam')

        # Кнопки: обычные, компактные, иконки, акцентные
        self._btn_style(st, 'Flat.TButton',  C['btn'],  C['btn_hover'],  C['btn_press'],  C['btn_fg'], (12, 6))
        self._btn_style(st, 'FlatSm.TButton', C['btn'], C['btn_hover'],  C['btn_press'],  C['btn_fg'], (8, 4))
        self._btn_style(st, 'Icon.TButton',  C['btn'],  C['btn_hover'],  C['btn_press'],  C['btn_fg'], (6, 2))
        self._btn_style(st, 'Run.TButton',   C['run'],  C['run_hover'],  C['run_press'],  '#FFFFFF',  (14, 6))
        self._btn_style(st, 'Stop.TButton',  C['stop'], C['stop_hover'], C['stop_press'], '#FFFFFF',  (14, 6))

        # Полосы прокрутки
        for orient in ('Vertical', 'Horizontal'):
            name = f'{orient}.TScrollbar'
            st.configure(name, background=C['scroll'], troughcolor=C['bg'],
                         bordercolor=C['bg'], arrowcolor=C['text_dim'],
                         lightcolor=C['scroll'], darkcolor=C['scroll'])
            st.map(name, background=[('active', C['scroll_hover'])])

        # Дерево проводника
        st.configure('Treeview', background=C['tree_bg'], fieldbackground=C['tree_bg'],
                     foreground=C['text'], rowheight=26, borderwidth=0, font=self.ui_font)
        st.configure('Treeview.Heading', background=C['panel'], foreground=C['text_dim'],
                     borderwidth=0, font=self.ui_bold)
        st.map('Treeview',
               background=[('selected', C['select'])],
               foreground=[('selected', '#FFFFFF')])

        # Разделители панелей
        st.configure('TPanedwindow', background=C['border'])
        st.configure('Sash', background=C['border'], sashthickness=4)

        # Тёмное меню (работает на Windows/Linux, macOS использует системное)
        self.option_add('*Menu.background', C['panel'])
        self.option_add('*Menu.foreground', C['text'])
        self.option_add('*Menu.activeBackground', C['select'])
        self.option_add('*Menu.activeForeground', '#FFFFFF')
        self.option_add('*Menu.borderWidth', 1)
        self.option_add('*Menu.relief', 'flat')
        self.option_add('*Menu.font', self.ui_font)

    # ------------------------- меню и тулбар -------------------------

    def _build_menu(self) -> None:
        acc = 'Cmd' if sys.platform == 'darwin' else 'Ctrl'
        bar = tk.Menu(self)

        fm = tk.Menu(bar, tearoff=False)
        fm.add_command(label='Новый', accelerator=f'{acc}+N', command=self._new_file)
        fm.add_command(label='Открыть…', accelerator=f'{acc}+O', command=self._open_dialog)
        fm.add_separator()
        fm.add_command(label='Сохранить', accelerator=f'{acc}+S', command=self._save_file)
        fm.add_command(label='Сохранить как…', command=self._save_file_as)
        fm.add_separator()
        fm.add_command(label='Выход', command=self._on_close)
        bar.add_cascade(label='Файл', menu=fm)

        rm = tk.Menu(bar, tearoff=False)
        rm.add_command(label='Запустить', accelerator='F5', command=self._run_code)
        rm.add_command(label='Остановить', command=self._stop_code)
        rm.add_separator()
        rm.add_command(label='Очистить консоль', command=self._clear_console)
        bar.add_cascade(label='Запуск', menu=rm)

        hm = tk.Menu(bar, tearoff=False)
        hm.add_command(label='О программе', command=self._about)
        bar.add_cascade(label='Справка', menu=hm)

        self.configure(menu=bar)

    def _build_toolbar(self) -> None:
        C = COLORS
        bar = tk.Frame(self, bg=C['panel'])
        bar.pack(side='top', fill='x')

        self.btn_run = ttk.Button(bar, style='Run.TButton', text='▶  Запустить',
                                  command=self._run_code)
        self.btn_run.pack(side='left', padx=(10, 6), pady=8)

        self.btn_stop = ttk.Button(bar, style='Stop.TButton', text='■  Стоп',
                                   command=self._stop_code, state='disabled')
        self.btn_stop.pack(side='left', padx=6, pady=8)

        tk.Frame(bar, bg=C['border'], width=1).pack(side='left', fill='y', padx=10, pady=10)

        ttk.Button(bar, style='Flat.TButton', text='Сохранить',
                   command=self._save_file).pack(side='left', padx=6, pady=8)
        ttk.Button(bar, style='Flat.TButton', text='Очистить консоль',
                   command=self._clear_console).pack(side='left', padx=6, pady=8)

        self.toolbar_file = tk.Label(bar, bg=C['panel'], fg=C['text_dim'],
                                     anchor='e', font=self.ui_font, text='файл не открыт')
        self.toolbar_file.pack(side='right', padx=12)

    # ------------------------- основной макет -------------------------

    def _build_main(self) -> None:
        # Горизонтальная панель: сайдбар | рабочая область
        self.paned_h = ttk.Panedwindow(self, orient='horizontal')
        self.paned_h.pack(fill='both', expand=True)

        self.sidebar = tk.Frame(self.paned_h, bg=COLORS['panel'])
        self.paned_h.add(self.sidebar, weight=0)

        right = tk.Frame(self.paned_h, bg=COLORS['bg'])
        self.paned_h.add(right, weight=1)

        self._build_sidebar()

        # Вертикальная панель: редактор | консоль
        self.paned_v = ttk.Panedwindow(right, orient='vertical')
        self.paned_v.pack(fill='both', expand=True)

        editor_box = tk.Frame(self.paned_v, bg=COLORS['bg'])
        self.paned_v.add(editor_box, weight=3)
        console_box = tk.Frame(self.paned_v, bg=COLORS['bg'])
        self.paned_v.add(console_box, weight=1)

        self._build_editor(editor_box)
        self._build_console(console_box)

        # Начальные позиции разделителей — после первой отрисовки окна
        self.bind('<Configure>', self._set_initial_sashes)

    def _set_initial_sashes(self, _event=None) -> None:
        if self._sashes_done:
            return
        self._sashes_done = True
        try:
            self.paned_h.sashpos(0, 272)
            self.paned_v.sashpos(0, int(self.paned_v.winfo_height() * 0.68))
        except tk.TclError:
            pass

    # ------------------------- сайдбар: проводник + шаблоны -------------------------

    def _build_sidebar(self) -> None:
        C = COLORS
        s = self.sidebar
        s.columnconfigure(0, weight=1)
        s.rowconfigure(1, weight=1)   # дерево растягивается по вертикали

        # Заголовок «Проводник» + кнопка обновления
        head = tk.Frame(s, bg=C['panel'])
        head.grid(row=0, column=0, sticky='ew', padx=8, pady=(10, 4))
        tk.Label(head, text='ПРОВОДНИК', bg=C['panel'], fg=C['text_dim'],
                 font=self.ui_small).pack(side='left')
        ttk.Button(head, style='Icon.TButton', text='⟳', width=3,
                   command=self._refresh_tree, takefocus=False).pack(side='right')

        # Дерево файлов с полосой прокрутки
        tree_box = tk.Frame(s, bg=C['panel'])
        tree_box.grid(row=1, column=0, sticky='nsew', padx=8)
        tree_box.rowconfigure(0, weight=1)
        tree_box.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(tree_box, show='tree', selectmode='browse')
        self.tree.grid(row=0, column=0, sticky='nsew')
        tsb = ttk.Scrollbar(tree_box, orient='vertical', command=self.tree.yview)
        tsb.grid(row=0, column=1, sticky='ns')
        self.tree.configure(yscrollcommand=tsb.set)
        self.tree.tag_configure('dir', foreground=C['dir'])
        self.tree.tag_configure('file', foreground=C['text'])

        # Заголовок «Шаблоны кода»
        head2 = tk.Frame(s, bg=C['panel'])
        head2.grid(row=2, column=0, sticky='ew', padx=8, pady=(12, 4))
        tk.Label(head2, text='ШАБЛОНЫ КОДА', bg=C['panel'], fg=C['text_dim'],
                 font=self.ui_small).pack(side='left')

        # Сетка кнопок быстрой вставки (2 колонки)
        snip = tk.Frame(s, bg=C['panel'])
        snip.grid(row=3, column=0, sticky='ew', padx=4, pady=(0, 10))
        snip.columnconfigure((0, 1), weight=1, uniform='snip')
        for i, (label, code, select) in enumerate(SNIPPETS):
            row, col = divmod(i, 2)
            ttk.Button(snip, style='FlatSm.TButton', text=label,
                       command=partial(self._insert_snippet, code, select)
                       ).grid(row=row, column=col, sticky='ew', padx=4, pady=4)

        self._add_tree_root()

    # ------------------------- редактор -------------------------

    def _build_editor(self, parent: tk.Frame) -> None:
        C = COLORS
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        self.editor = tk.Text(
            parent, bg=C['bg'], fg=C['text'],
            insertbackground=C['caret'], insertwidth=2,
            selectbackground=C['select'], selectforeground='#FFFFFF',
            inactiveselectbackground=C['select'],
            relief='flat', bd=0, highlightthickness=0,
            wrap='none', font=self.mono_font,
            undo=True, autoseparators=True, maxundo=1024,
            padx=12, pady=10,
            tabs=(self.mono_font.measure('    '),),   # ширина таба = 4 пробела
        )
        self.editor.grid(row=0, column=0, sticky='nsew')

        vsb = ttk.Scrollbar(parent, orient='vertical', command=self.editor.yview)
        vsb.grid(row=0, column=1, sticky='ns')
        hsb = ttk.Scrollbar(parent, orient='horizontal', command=self.editor.xview)
        hsb.grid(row=1, column=0, sticky='ew')
        self.editor.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # Теги подсветки синтаксиса
        tag_styles = {
            'keyword':   (C['kw'],      self.mono_bold),
            'string':    (C['string'],  self.mono_font),
            'comment':   (C['comment'], self.mono_italic),
            'number':    (C['number'],  self.mono_font),
            'funcname':  (C['func'],    self.mono_bold),
            'builtin':   (C['builtin'], self.mono_font),
            'selfkw':    (C['selfkw'],  self.mono_italic),
            'decorator': (C['decor'],   self.mono_font),
        }
        for name, (fg, font) in tag_styles.items():
            self.editor.tag_configure(name, foreground=fg, font=font)

    # ------------------------- консоль -------------------------

    def _build_console(self, parent: tk.Frame) -> None:
        C = COLORS
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        # Шапка консоли
        head = tk.Frame(parent, bg=C['panel'])
        head.grid(row=0, column=0, columnspan=2, sticky='ew')
        tk.Label(head, text='КОНСОЛЬ', bg=C['panel'], fg=C['text_dim'],
                 font=self.ui_small).pack(side='left', padx=12, pady=6)
        self.run_status = tk.Label(head, bg=C['panel'], fg=C['text_dim'], font=self.ui_font)
        self.run_status.pack(side='left', padx=6)
        ttk.Button(head, style='FlatSm.TButton', text='Очистить',
                   command=self._clear_console, takefocus=False
                   ).pack(side='right', padx=8, pady=4)

        # Поле вывода (только чтение)
        self.console = tk.Text(
            parent, bg=C['bg2'], fg=C['text'], insertbackground=C['caret'],
            relief='flat', bd=0, highlightthickness=0,
            wrap='word', font=self.console_font,
            state='disabled', cursor='arrow', padx=12, pady=8,
        )
        self.console.grid(row=1, column=0, sticky='nsew')
        csb = ttk.Scrollbar(parent, orient='vertical', command=self.console.yview)
        csb.grid(row=1, column=1, sticky='ns')
        self.console.configure(yscrollcommand=csb.set)

        self.console.tag_configure('stdout', foreground=C['text'])
        self.console.tag_configure('stderr', foreground=C['err'])
        self.console.tag_configure('info', foreground=C['text_dim'], font=self.console_italic)
        self.console.tag_configure('ok', foreground=C['ok'])

    def _console_write(self, tag: str, text: str) -> None:
        """Потокобезопасная запись в консоль через очередь + after()."""
        self.console.configure(state='normal')
        self.console.insert('end', text, tag)
        self.console.see('end')
        self.console.configure(state='disabled')

    def _clear_console(self, _event=None) -> None:
        self.console.configure(state='normal')
        self.console.delete('1.0', 'end')
        self.console.configure(state='disabled')

    # ------------------------- статусбар -------------------------

    def _build_statusbar(self) -> None:
        C = COLORS
        st = tk.Frame(self, bg=C['panel2'])
        st.pack(side='bottom', fill='x')

        self.status_path = tk.Label(st, bg=C['panel2'], fg=C['text_dim'],
                                    anchor='w', font=self.ui_font, text='Файл не открыт')
        self.status_path.pack(side='left', padx=10, pady=4)

        tk.Label(st, bg=C['panel2'], fg=C['text_dim'], font=self.ui_font,
                 text=f'Python {sys.version.split()[0]}  ·  UTF-8').pack(side='right', padx=10)
        self.status_pos = tk.Label(st, bg=C['panel2'], fg=C['text_dim'],
                                   font=self.ui_font, text='Стр 1, стлб 1')
        self.status_pos.pack(side='right', padx=6)

    # ------------------------- события -------------------------

    def _bind_events(self) -> None:
        mod = 'Command' if sys.platform == 'darwin' else 'Control'
        self.bind_all(f'<{mod}-n>', self._new_file)
        self.bind_all(f'<{mod}-o>', self._open_dialog)
        self.bind_all(f'<{mod}-s>', self._save_file)
        self.bind_all('<F5>', self._run_code)
        self.bind_all(f'<{mod}-Return>', self._run_code)

        ed = self.editor
        ed.bind('<Return>', self._on_return)          # умный автоотступ
        ed.bind('<Tab>', self._on_tab)                # отступ блока / 4 пробела
        for seq in ('<Shift-Tab>', '<ISO_Left_Tab>'):
            ed.bind(seq, self._on_shift_tab)          # сдвиг блока влево
        ed.bind('<<Modified>>', self._on_editor_modified)
        ed.bind('<KeyRelease>', self._update_cursor_pos)
        ed.bind('<ButtonRelease-1>', self._update_cursor_pos)

        self.tree.bind('<Double-Button-1>', self._on_tree_dclick)
        self.tree.bind('<Return>', lambda _e: self._tree_activate(self.tree.focus()))
        self.tree.bind('<<TreeviewOpen>>', self._on_tree_open)

    def _update_cursor_pos(self, _event=None) -> None:
        try:
            line, col = self.editor.index('insert').split('.')
            self.status_pos.configure(text=f'Стр {line}, стлб {int(col) + 1}')
        except tk.TclError:
            pass

    # ============================================================
    # 4. ПОДСВЕТКА СИНТАКСИСА
    # ============================================================

    def _on_editor_modified(self, _event=None) -> None:
        """Срабатывает при любом изменении текста; перезапускает подсветку."""
        if not self.editor.edit_modified():
            return
        self.editor.edit_modified(False)   # сброс, чтобы следующее изменение снова дало событие
        self.modified = True
        self._update_title()
        self._schedule_highlight()

    def _schedule_highlight(self) -> None:
        """Дебаунс: не перерисовываем подсветку чаще, чем раз в 200 мс."""
        if self._hl_after is not None:
            self.after_cancel(self._hl_after)
        self._hl_after = self.after(200, self._highlight)

    def _highlight(self) -> None:
        """Полная перерисовка подсветки по регулярному выражению."""
        if self._hl_after is not None:
            self.after_cancel(self._hl_after)
            self._hl_after = None

        ed = self.editor
        content = ed.get('1.0', 'end-1c')
        for tag in HIGHLIGHT_TAGS:
            ed.tag_remove(tag, '1.0', 'end')
        if not content:
            return

        # Смещение в символах -> индекс вида "1.0+Nc" (tkinter считает сам)
        for m in HIGHLIGHT_RE.finditer(content):
            tag = m.lastgroup
            if tag:
                start, end = m.span()
                ed.tag_add(tag, f'1.0+{start}c', f'1.0+{end}c')

    # ============================================================
    # 5. УМНЫЕ АВТООТСТУПЫ И ОТСТУПЫ БЛОКА
    # ============================================================

    def _on_return(self, _event) -> str:
        """Enter: наследуем отступ строки; после «:» добавляем ещё 4 пробела."""
        ed = self.editor
        try:                                   # если есть выделение — заменяем его
            ed.delete('sel.first', 'sel.last')
        except tk.TclError:
            pass

        line, col = ed.index('insert').split('.')
        before = ed.get(f'{line}.0', f'{line}.{col}')       # текст до курсора
        indent = re.match(r'[ \t]*', before).group(0)       # текущий отступ

        # Двоеточие в конце (возможно, с комментарием после него)
        extra = '    ' if re.search(r':\s*(#.*)?$', before.rstrip()) else ''
        ed.insert('insert', '\n' + indent + extra)
        ed.see('insert')
        return 'break'

    def _on_tab(self, _event) -> str:
        """Tab: 4 пробела либо отступ выделенного блока."""
        ed = self.editor
        try:
            first, last = ed.index('sel.first'), ed.index('sel.last')
        except tk.TclError:
            ed.insert('insert', '    ')
            return 'break'
        self._indent_block(first, last, outdent=False)
        return 'break'

    def _on_shift_tab(self, _event) -> str:
        """Shift+Tab: сдвиг блока (или текущей строки) влево."""
        ed = self.editor
        try:
            first, last = ed.index('sel.first'), ed.index('sel.last')
        except tk.TclError:
            self._dedent_line(int(ed.index('insert').split('.')[0]))
            return 'break'
        self._indent_block(first, last, outdent=True)
        return 'break'

    def _indent_block(self, first: str, last: str, outdent: bool) -> None:
        ed = self.editor
        l1 = int(first.split('.')[0])
        l2 = int(last.split('.')[0])
        if last.split('.')[1] == '0' and l2 > l1:   # выделение кончается в начале строки
            l2 -= 1
        for ln in range(l1, l2 + 1):
            if outdent:
                self._dedent_line(ln)
            else:
                ed.insert(f'{ln}.0', '    ')

    def _dedent_line(self, ln: int) -> None:
        ed = self.editor
        head = ed.get(f'{ln}.0', f'{ln}.end')
        n = min(4, len(head) - len(head.lstrip(' ')))
        if n:
            ed.delete(f'{ln}.0', f'{ln}.{n}')

    # ============================================================
    # 6. ВСТАВКА ШАБЛОНОВ КОДА
    # ============================================================

    def _insert_snippet(self, code: str, select: str | None = None) -> None:
        """Вставляет шаблон ровно в позицию курсора и возвращает фокус."""
        ed = self.editor
        ed.focus_set()
        try:                                   # заменяем выделение, если оно есть
            ed.delete('sel.first', 'sel.last')
        except tk.TclError:
            pass

        start = ed.index('insert')
        ed.insert('insert', code)

        if select:                             # выделяем «заполнитель» в шаблоне
            pos = code.find(select)
            if pos >= 0:
                a = f'{start}+{pos}c'
                b = f'{start}+{pos + len(select)}c'
                ed.tag_remove('sel', '1.0', 'end')
                ed.tag_add('sel', a, b)
                ed.mark_set('insert', a)

        self._update_cursor_pos()
        ed.focus_set()

    # ============================================================
    # 7. ПРОВОДНИК ФАЙЛОВ
    # ============================================================

    @staticmethod
    def _dummy(iid: str) -> str:
        """iid «пустышки», чтобы у папки был треугольник раскрытия."""
        return iid + '\x00d'

    def _add_tree_root(self) -> None:
        self.tree.delete(*self.tree.get_children())
        name = os.path.basename(SCRIPT_DIR) or SCRIPT_DIR
        self.tree.insert('', 'end', iid=SCRIPT_DIR, text=name,
                         open=True, tags=('dir',))
        self._populate_tree(SCRIPT_DIR)

    def _refresh_tree(self) -> None:
        self._add_tree_root()

    def _populate_tree(self, folder: str) -> None:
        """Лениво наполняет папку: каталоги (с пустышкой) и файлы .py."""
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return
        entries.sort(key=lambda e: (not e.is_dir(), e.name.lower()))
        for entry in entries:
            if entry.name in HIDDEN:
                continue
            if entry.is_dir():
                self.tree.insert(folder, 'end', iid=entry.path,
                                 text=entry.name, tags=('dir',))
                self.tree.insert(entry.path, 'end', iid=self._dummy(entry.path),
                                 text='', tags=('dummy',))
            elif entry.name.lower().endswith(('.py', '.pyw')):
                self.tree.insert(folder, 'end', iid=entry.path,
                                 text=entry.name, tags=('file',))

    def _ensure_populated(self, iid: str) -> None:
        """Заменяет «пустышку» реальным содержимым папки."""
        children = self.tree.get_children(iid)
        if len(children) == 1 and 'dummy' in self.tree.item(children[0], 'tags'):
            self.tree.delete(children[0])
            self._populate_tree(iid)

    def _on_tree_open(self, _event=None) -> None:
        self._ensure_populated(self.tree.focus())

    def _on_tree_dclick(self, event) -> str:
        iid = self.tree.identify_row(event.y)
        self._tree_activate(iid)
        return 'break'

    def _tree_activate(self, iid: str) -> None:
        """Двойной клик / Enter: папки раскрываем, файлы .py открываем."""
        if not iid or '\x00' in iid:
            return
        if os.path.isdir(iid):
            if self.tree.item(iid, 'open'):
                self.tree.item(iid, open=False)
            else:
                self._ensure_populated(iid)
                self.tree.item(iid, open=True)
        elif os.path.isfile(iid) and iid.lower().endswith(('.py', '.pyw')):
            self._open_path(iid)

    # ============================================================
    # 8. ФАЙЛОВЫЕ ОПЕРАЦИИ
    # ============================================================

    @staticmethod
    def _shorten(text: str, limit: int = 48) -> str:
        return text if len(text) <= limit else '…' + text[-(limit - 1):]

    @staticmethod
    def _read_file(path: str) -> tuple[str | None, str | None]:
        """Чтение с перебором кодировок (актуально для cp1251)."""
        for enc in ('utf-8-sig', 'utf-8', 'cp1251', 'latin-1'):
            try:
                with open(path, 'r', encoding=enc) as fh:
                    return fh.read(), enc
            except UnicodeDecodeError:
                continue
            except OSError as exc:
                messagebox.showerror('PyEdit', f'Не удалось открыть файл:\n{exc}')
                return None, None
        return None, None

    def _set_editor_text(self, text: str) -> None:
        ed = self.editor
        ed.configure(state='normal')
        ed.delete('1.0', 'end')
        ed.insert('1.0', text)
        ed.edit_reset()               # очистка истории undo
        ed.edit_modified(False)
        ed.mark_set('insert', '1.0')
        ed.see('1.0')
        self.modified = False
        self._highlight()
        self._update_cursor_pos()

    def _confirm_keep_changes(self) -> bool:
        """False = пользователь нажал «Отмена», действие прерываем."""
        if not self.modified:
            return True
        ans = messagebox.askyesnocancel(
            'PyEdit', 'Сохранить изменения перед продолжением?')
        if ans is None:
            return False
        if ans:
            return self._save_file()
        return True

    def _open_path(self, path: str) -> None:
        if not os.path.isfile(path):
            return
        if not self._confirm_keep_changes():
            return
        text, _enc = self._read_file(path)
        if text is None:
            return
        self._set_editor_text(text)
        self.current_path = path
        self._after_file_changed()

    def _new_file(self, _event=None) -> None:
        if not self._confirm_keep_changes():
            return
        self._set_editor_text('')
        self.current_path = None
        self._after_file_changed()

    def _open_dialog(self, _event=None) -> None:
        if not self._confirm_keep_changes():
            return
        initial = os.path.dirname(self.current_path) if self.current_path else SCRIPT_DIR
        path = filedialog.askopenfilename(
            parent=self, initialdir=initial,
            filetypes=[('Файлы Python', '*.py *.pyw'), ('Все файлы', '*.*')])
        if path:
            self._open_path(path)

    def _save_file(self, _event=None) -> bool:
        path = self.current_path
        if not path:
            path = filedialog.asksaveasfilename(
                parent=self, defaultextension='.py', initialfile='untitled.py',
                filetypes=[('Файлы Python', '*.py *.pyw'), ('Все файлы', '*.*')])
            if not path:
                return False
        try:
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(self.editor.get('1.0', 'end-1c'))
        except OSError as exc:
            messagebox.showerror('PyEdit', f'Не удалось сохранить файл:\n{exc}')
            return False
        self.current_path = path
        self.modified = False
        self.editor.edit_modified(False)
        self._after_file_changed()
        return True

    def _save_file_as(self) -> None:
        old = self.current_path
        self.current_path = None
        if not self._save_file():
            self.current_path = old
            self._after_file_changed()

    def _after_file_changed(self) -> None:
        self._update_title()
        if self.current_path:
            pretty = self._shorten(self.current_path)
            self.toolbar_file.configure(text=pretty)
            self.status_path.configure(text=pretty)
        else:
            self.toolbar_file.configure(text='файл не открыт')
            self.status_path.configure(text='Файл не открыт')
        self._update_cursor_pos()

    def _update_title(self) -> None:
        name = os.path.basename(self.current_path) if self.current_path else 'без имени.py'
        star = ' •' if self.modified else ''
        self.title(f'{name}{star} — PyEdit')

    # ============================================================
    # 9. ЗАПУСК КОДА (subprocess + потоки + очередь)
    # ============================================================

    def _run_code(self, _event=None) -> None:
        if self.process is not None and self.process.poll() is None:
            return
        code = self.editor.get('1.0', 'end-1c')
        if not code.strip():
            self._console_write('info', '\nНечего запускать — редактор пуст.\n')
            return

        # Сохраняем код во временный файл
        try:
            fd, tmp = tempfile.mkstemp(prefix='pyedit_', suffix='.py')
            with os.fdopen(fd, 'w', encoding='utf-8') as fh:
                fh.write(code)
        except OSError as exc:
            self._console_write('stderr', f'Не удалось создать временный файл: {exc}\n')
            return
        self._temp_path = tmp

        self._clear_console()
        name = os.path.basename(self.current_path) if self.current_path else '<без имени>'
        self._console_write('info',
                            f'─── Запуск {name} · {datetime.now():%H:%M:%S} ───\n')

        env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
        cwd = os.path.dirname(self.current_path) if self.current_path else SCRIPT_DIR

        startupinfo = None
        if os.name == 'nt':   # не показывать консольное окно дочернего процесса
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        try:
            self.process = subprocess.Popen(
                [sys.executable, tmp],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                cwd=cwd, env=env, startupinfo=startupinfo,
                text=True, encoding='utf-8', errors='replace', bufsize=1,
            )
        except OSError as exc:
            self._console_write('stderr', f'Не удалось запустить процесс: {exc}\n')
            self.process = None
            return

        # Два фоновых потока читают stdout/stderr и складывают строки в очередь
        self._run_start = time.monotonic()
        self._readers = [
            threading.Thread(target=self._pipe_reader,
                             args=(self.process.stdout, 'stdout'), daemon=True),
            threading.Thread(target=self._pipe_reader,
                             args=(self.process.stderr, 'stderr'), daemon=True),
        ]
        for t in self._readers:
            t.start()

        self.btn_run.configure(state='disabled')
        self.btn_stop.configure(state='normal')
        self.run_status.configure(text='выполняется…')

    def _pipe_reader(self, pipe, tag: str) -> None:
        """Работает в отдельном потоке: читает поток процесса построчно."""
        try:
            for line in pipe:
                self.output_queue.put((tag, line))
        except ValueError:
            pass
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    def _poll_output(self) -> None:
        """Периодически перекладывает очередь в консоль (безопасно для tkinter)."""
        try:
            while True:
                tag, chunk = self.output_queue.get_nowait()
                self._console_write(tag, chunk)
        except queue.Empty:
            pass

        proc = self.process
        if proc is not None and proc.poll() is not None:
            readers_done = all(not t.is_alive() for t in self._readers)
            if readers_done and self.output_queue.empty():
                rc = proc.returncode
                elapsed = time.monotonic() - self._run_start
                if rc == 0:
                    self._console_write('ok', f'\nГотово за {elapsed:.2f} с (код 0)\n')
                else:
                    self._console_write('stderr', f'\nПроцесс завершился с кодом {rc}\n')
                self.run_status.configure(text=f'код {rc}')
                self._cleanup_run()

        self.after(80, self._poll_output)

    def _cleanup_run(self) -> None:
        if self._temp_path:
            try:
                os.remove(self._temp_path)
            except OSError:
                pass
            self._temp_path = None
        self.process = None
        self._readers = []
        self.btn_run.configure(state='normal')
        self.btn_stop.configure(state='disabled')

    def _stop_code(self, _event=None) -> None:
        proc = self.process
        if proc is None or proc.poll() is not None:
            return
        self._console_write('info', '\nОстанавливаю процесс…\n')
        try:
            if os.name == 'nt':   # убиваем всё дерево процессов
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                proc.terminate()
        except OSError:
            pass

    # ============================================================
    # 10. ПРОЧЕЕ
    # ============================================================

    def _about(self) -> None:
        messagebox.showinfo(
            'О программе',
            'PyEdit — учебный редактор Python-кода.\n'
            'Сделано на tkinter/ttk: подсветка синтаксиса, умные отступы,\n'
            'проводник файлов, шаблоны кода и запуск скриптов.\n\n'
            'Горячие клавиши: Ctrl+N/O/S, F5 — запуск, Tab/Shift+Tab — отступы.',
            parent=self)

    def _on_close(self, _event=None) -> None:
        if not self._confirm_keep_changes():
            return
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.terminate()
            except OSError:
                pass
        if self._temp_path:
            try:
                os.remove(self._temp_path)
            except OSError:
                pass
        self.destroy()


# ============================================================
# ТОЧКА ВХОДА
# ============================================================

def main() -> None:
    _enable_dpi()
    app = PyEdit()
    app.mainloop()


if __name__ == '__main__':
    main()