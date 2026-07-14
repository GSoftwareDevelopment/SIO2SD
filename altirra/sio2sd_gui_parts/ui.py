"""SIO2SDGuiUiMixin."""

import tkinter as tk
from tkinter import ttk


class SIO2SDGuiUiMixin:
    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        root = ttk.Frame(self, padding=10)
        root.pack(fill='both', expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        root.rowconfigure(1, weight=0)

        notebook = ttk.Notebook(root)
        notebook.grid(row=0, column=0, sticky='nsew')

        status_bar = ttk.Frame(root)
        status_bar.grid(row=1, column=0, sticky='ew', pady=(8, 0))
        status_bar.columnconfigure(0, weight=1)
        ttk.Label(status_bar, textvariable=self.status).grid(
            row=0, column=0, sticky='w')
        status_leds = ttk.Frame(status_bar)
        status_leds.grid(row=0, column=1, sticky='e', padx=(12, 0))
        for name, color in (('SIOACT', '#d12a2a'),
                            ('SDACT', '#33c65a'),
                            ('ERROR', '#d12a2a')):
            self._add_status_led(status_leds, name, color)
        ttk.Button(status_bar, text='Mini LCD',
                   command=self._show_mini).grid(row=0, column=2,
                                                 sticky='e', padx=(12, 0))

        sio_tab = ttk.Frame(notebook, padding=10)
        sd_tab = ttk.Frame(notebook, padding=10)
        server_tab = ttk.Frame(notebook, padding=10)
        drives_tab = ttk.Frame(notebook, padding=10)
        log_tab = ttk.Frame(notebook, padding=10)
        notebook.add(sio_tab, text='SIO2SD')
        notebook.add(sd_tab, text='Karta SD')
        notebook.add(drives_tab, text='Napedy')
        notebook.add(server_tab, text='Server')
        notebook.add(log_tab, text='Log')

        sio_tab.columnconfigure(0, weight=1)
        sd_tab.columnconfigure(0, weight=1)
        sd_tab.rowconfigure(1, weight=1)
        server_tab.columnconfigure(0, weight=1)
        drives_tab.rowconfigure(0, weight=2)
        drives_tab.rowconfigure(1, weight=1)
        drives_tab.columnconfigure(0, weight=1)
        log_tab.rowconfigure(0, weight=1)
        log_tab.columnconfigure(0, weight=1)

        settings = ttk.LabelFrame(sd_tab, text='Karta SD', padding=8)
        settings.grid(row=0, column=0, sticky='ew')
        settings.columnconfigure(1, weight=1)

        ttk.Label(settings, text='Katalog SD').grid(row=0, column=0, sticky='w')
        ttk.Entry(settings, textvariable=self.sd_dir).grid(
            row=0, column=1, sticky='ew', padx=(8, 6))
        ttk.Button(settings, text='Wybierz', command=self._browse_sd).grid(
            row=0, column=2, sticky='ew')
        ttk.Button(settings, text='Otworz Atari',
                   command=self._open_card_root).grid(row=0, column=3,
                                                       sticky='ew', padx=(6, 0))

        ttk.Label(settings, text='Katalog Atari').grid(row=1, column=0,
                                                       sticky='w', pady=(6, 0))
        ttk.Label(settings, textvariable=self.card_root).grid(
            row=1, column=1, columnspan=3, sticky='w', padx=(8, 0), pady=(6, 0))

        server_frame = ttk.LabelFrame(server_tab, text='Server', padding=8)
        server_frame.grid(row=0, column=0, sticky='ew')
        server_frame.columnconfigure(0, weight=1)

        controls = ttk.Frame(server_frame)
        controls.grid(row=0, column=0, sticky='ew')

        ttk.Label(controls, text='Port').pack(side='left')
        tk.Spinbox(controls, textvariable=self.port, from_=1, to=65535,
                   width=7).pack(side='left', padx=(6, 14))

        ttk.Checkbutton(controls, text='Tylko odczyt',
                        variable=self.read_only).pack(side='left', padx=(0, 14))
        ttk.Checkbutton(controls, text='Auto start',
                        variable=self.auto_start).pack(side='left')
        ttk.Checkbutton(controls, text='CFG selector',
                        variable=self.cfg_selector).pack(side='left',
                                                         padx=(14, 0))

        ttk.Button(controls, text='Start', command=self._start_server).pack(
            side='right', padx=(6, 0))
        ttk.Button(controls, text='Stop', command=self._stop_server).pack(
            side='right')

        checklist = ttk.LabelFrame(server_tab, text='Checklista Altirry',
                                   padding=8)
        checklist.grid(row=1, column=0, sticky='ew', pady=(10, 0))
        checklist.columnconfigure(0, weight=1)
        checklist.columnconfigure(1, weight=1)

        self._add_check_item(checklist, 0, 0, 'card_root',
                             self.check_card_root)
        self._add_check_item(checklist, 0, 1, 'device_file',
                             self.check_device_file, padx=(12, 0))
        self._add_check_item(checklist, 1, 0, 'server',
                             self.check_server, pady=(4, 0))
        self._add_check_item(checklist, 1, 1, 'connection',
                             self.check_connection, padx=(12, 0),
                             pady=(4, 0))

        config_frame = ttk.LabelFrame(sio_tab, text='Ustawienia SIO2SD',
                                      padding=8)
        config_frame.grid(row=0, column=0, sticky='ew')
        config_frame.columnconfigure(5, weight=1)

        ttk.Checkbutton(config_frame, text='Widoczny dla Atari',
                        variable=self.device_visible).grid(
                            row=0, column=0, columnspan=6, sticky='w')

        ttk.Label(config_frame, text='ID').grid(row=1, column=0, sticky='w',
                                                pady=(8, 0))
        ttk.Combobox(config_frame, textvariable=self.device_id,
                     values=('0', '1', '2', '3'), width=4,
                     state='readonly').grid(row=1, column=1, sticky='w',
                                            padx=(8, 18), pady=(8, 0))
        ttk.Label(config_frame, text='hIndex').grid(row=1, column=2,
                                                    sticky='w', pady=(8, 0))
        tk.Spinbox(config_frame, textvariable=self.cfg_hsindex,
                   from_=0, to=255, width=5).grid(row=1, column=3,
                                                  sticky='w', padx=(8, 18),
                                                  pady=(8, 0))
        ttk.Label(config_frame, text='Turbo hIndex').grid(row=1, column=4,
                                                          sticky='w',
                                                          pady=(8, 0))
        tk.Spinbox(config_frame, textvariable=self.cfg_turbo_hsindex,
                   from_=0, to=255, width=5).grid(row=1, column=5,
                                                  sticky='w', padx=(8, 0),
                                                  pady=(8, 0))
        ttk.Checkbutton(config_frame, text='Ochrona ATR wg configu',
                        variable=self.cfg_atr_write_protect).grid(
                            row=2, column=0, columnspan=2, sticky='w',
                            pady=(8, 0))
        ttk.Checkbutton(config_frame, text='TopDrive turbo',
                        variable=self.topdrive_turbo).grid(
                            row=2, column=2, columnspan=4, sticky='w',
                            pady=(8, 0))

        raw_frame = ttk.LabelFrame(config_frame, text='Blok $12 / $13',
                                   padding=6)
        raw_frame.grid(row=3, column=0, columnspan=6, sticky='ew',
                       pady=(10, 0))
        for col in range(8):
            raw_frame.columnconfigure(col, weight=1)
        for idx, variable in enumerate(self.cfg_byte_vars):
            row = 0 if idx < 8 else 2
            col = idx % 8
            ttk.Label(raw_frame, text='%02X' % idx).grid(
                row=row, column=col, sticky='w')
            tk.Spinbox(raw_frame, textvariable=variable, from_=0, to=255,
                       width=4).grid(row=row + 1, column=col, sticky='w',
                                     padx=(0, 8), pady=(2, 6))
        ttk.Label(raw_frame, textvariable=self.cfg_raw,
                  font=('Consolas', 9)).grid(row=4, column=0, columnspan=8,
                                             sticky='w', pady=(2, 0))

        config_buttons = ttk.Frame(config_frame)
        config_buttons.grid(row=4, column=0, columnspan=6, sticky='ew',
                            pady=(8, 0))
        ttk.Button(config_buttons, text='Odczytaj',
                   command=self._read_sio2sd_config).pack(side='left')
        ttk.Button(config_buttons, text='Zastosuj',
                   command=self._apply_sio2sd_config).pack(side='left',
                                                           padx=(6, 0))
        ttk.Label(config_buttons, textvariable=self.cfg_status).pack(
            side='left', padx=(12, 0))

        hardware_frame = ttk.LabelFrame(sio_tab, text='Opcje sprzetowe',
                                        padding=8)
        hardware_frame.grid(row=1, column=0, sticky='ew', pady=(10, 0))
        hardware_frame.columnconfigure(0, weight=1)
        hardware_notes = (
            'Shift przy wlaczeniu zasilania i loader turbo: zachowanie '
            'sprzetowe, poza emulacja Altirry.',
            'Tryb wskazan diod i czasy repetycji klawiatury: dotycza '
            'panelu fizycznego SIO2SD.',
            'Aktualizacja wsadu z SIO2SD.BIN: nie dotyczy emulatora; '
            'tu emulujemy zachowanie firmware w Pythonie.',
        )
        for row, text in enumerate(hardware_notes):
            ttk.Label(hardware_frame, text=text, foreground='#555555',
                      wraplength=760).grid(row=row, column=0, sticky='w',
                                           pady=(0 if row == 0 else 4, 0))

        files_frame = ttk.LabelFrame(sd_tab, text='Pliki karty', padding=8)
        files_frame.grid(row=1, column=0, sticky='nsew', pady=(10, 0))
        files_frame.rowconfigure(2, weight=1)
        files_frame.columnconfigure(0, weight=1)

        file_controls = ttk.Frame(files_frame)
        file_controls.grid(row=0, column=0, columnspan=2, sticky='ew',
                           pady=(0, 8))

        ttk.Label(file_controls, text='Filtr').pack(side='left')
        ttk.Combobox(
            file_controls,
            textvariable=self.file_filter,
            values=('Obrazy i programy', 'ATR', 'XEX/COM/EXE', 'RAW', 'Wszystkie'),
            width=18,
            state='readonly').pack(side='left', padx=(6, 14))

        ttk.Label(file_controls, text='Szukaj').pack(side='left')
        search_entry = ttk.Entry(file_controls, textvariable=self.file_search,
                                 width=22)
        search_entry.pack(side='left', padx=(6, 14))
        search_entry.bind('<Return>', lambda _event: self._refresh_files())

        ttk.Label(file_controls, text='Do napedu').pack(side='left')
        ttk.Combobox(
            file_controls,
            textvariable=self.browser_drive,
            values=tuple('D%d:' % n for n in range(1, 16)),
            width=5,
            state='readonly').pack(side='left', padx=(6, 14))

        ttk.Button(file_controls, text='Montuj zaznaczony',
                   command=self._mount_selected_file).pack(side='left')
        ttk.Button(file_controls, text='Odswiez pliki',
                   command=self._refresh_files).pack(side='right')

        ttk.Label(files_frame,
                  text='Dwuklik montuje zaznaczony plik do wybranego napedu.',
                  foreground='#555555').grid(row=1, column=0, columnspan=2,
                                             sticky='w', pady=(0, 6))

        self.files = ttk.Treeview(
            files_frame,
            columns=('kind', 'size', 'path'),
            show='tree headings',
            selectmode='browse',
            height=10)
        self.files.heading('#0', text='Nazwa')
        self.files.heading('kind', text='Typ')
        self.files.heading('size', text='Rozmiar')
        self.files.heading('path', text='Sciezka')
        self.files.column('#0', width=220)
        self.files.column('kind', width=95, stretch=False)
        self.files.column('size', width=90, stretch=False, anchor='e')
        self.files.column('path', width=420)
        self.files.grid(row=2, column=0, sticky='nsew')
        self.files.bind('<Double-1>', lambda _event: self._mount_selected_file())

        file_scroll = ttk.Scrollbar(files_frame, orient='vertical',
                                    command=self.files.yview)
        file_scroll.grid(row=2, column=1, sticky='ns')
        self.files.configure(yscrollcommand=file_scroll.set)

        drives_frame = ttk.LabelFrame(drives_tab, text='Napedy D1:-D15:',
                                      padding=8)
        drives_frame.grid(row=0, column=0, sticky='nsew')
        drives_frame.rowconfigure(0, weight=1)
        drives_frame.columnconfigure(0, weight=1)

        self.drives = ttk.Treeview(
            drives_frame,
            columns=('map', 'status', 'file', 'type', 'sectors', 'ro'),
            show='tree headings',
            selectmode='browse',
            height=15)
        self.drives.heading('#0', text='Naped')
        self.drives.heading('map', text='Mapowanie')
        self.drives.heading('status', text='Status')
        self.drives.heading('file', text='Plik')
        self.drives.heading('type', text='Typ')
        self.drives.heading('sectors', text='Sektory')
        self.drives.heading('ro', text='RO')
        self.drives.column('#0', width=70, stretch=False)
        self.drives.column('map', width=95, stretch=False)
        self.drives.column('status', width=95, stretch=False)
        self.drives.column('file', width=350)
        self.drives.column('type', width=100, stretch=False)
        self.drives.column('sectors', width=80, stretch=False, anchor='e')
        self.drives.column('ro', width=50, stretch=False, anchor='center')
        self.drives.grid(row=0, column=0, sticky='nsew')
        self.drives.bind('<<TreeviewSelect>>', self._drive_selection_changed)

        scroll = ttk.Scrollbar(drives_frame, orient='vertical',
                               command=self.drives.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        self.drives.configure(yscrollcommand=scroll.set)

        drive_buttons = ttk.Frame(drives_frame)
        drive_buttons.grid(row=1, column=0, columnspan=2, sticky='ew',
                           pady=(8, 0))
        ttk.Button(drive_buttons, text='Montuj plik',
                   command=self._mount_file).pack(side='left')
        ttk.Button(drive_buttons, text='Pusty dysk',
                   command=self._mount_empty).pack(side='left', padx=(6, 0))
        if self.SHOW_EXPERIMENTAL_ATR_CREATOR:
            ttk.Button(drive_buttons, text='Nowy ATR',
                       command=self._create_atr_drive).pack(side='left',
                                                            padx=(6, 0))
        ttk.Button(drive_buttons, text='Odmontuj',
                   command=self._unmount).pack(side='left', padx=(6, 0))
        ttk.Button(drive_buttons, text='D -> V',
                   command=self._map_drive_to_virtual).pack(side='left',
                                                            padx=(12, 0))
        ttk.Button(drive_buttons, text='D -> D',
                   command=self._reset_drive_mapping).pack(side='left',
                                                           padx=(6, 0))
        ttk.Button(drive_buttons, text='Zamien D/V',
                   command=self._swap_drive_virtual).pack(side='left',
                                                          padx=(6, 0))
        ttk.Checkbutton(drive_buttons, text='Zachowaj mapowanie',
                        variable=self.preserve_drive_mapping).pack(
                            side='left', padx=(12, 0))
        ttk.Button(drive_buttons, text='Odswiez',
                   command=self._refresh_drives).pack(side='right')

        virtual_frame = ttk.LabelFrame(drives_tab,
                                       text='Sloty wirtualne V1:-V99',
                                       padding=8)
        virtual_frame.grid(row=1, column=0, sticky='nsew', pady=(10, 0))
        virtual_frame.rowconfigure(0, weight=1)
        virtual_frame.columnconfigure(0, weight=1)

        self.virtuals = ttk.Treeview(
            virtual_frame,
            columns=('status', 'file', 'type', 'sectors', 'ro'),
            show='tree headings',
            selectmode='browse',
            height=7)
        self.virtuals.heading('#0', text='Slot')
        self.virtuals.heading('status', text='Status')
        self.virtuals.heading('file', text='Plik')
        self.virtuals.heading('type', text='Typ')
        self.virtuals.heading('sectors', text='Sektory')
        self.virtuals.heading('ro', text='RO')
        self.virtuals.column('#0', width=70, stretch=False)
        self.virtuals.column('status', width=95, stretch=False)
        self.virtuals.column('file', width=445)
        self.virtuals.column('type', width=100, stretch=False)
        self.virtuals.column('sectors', width=80, stretch=False, anchor='e')
        self.virtuals.column('ro', width=50, stretch=False, anchor='center')
        self.virtuals.grid(row=0, column=0, sticky='nsew')

        virtual_scroll = ttk.Scrollbar(virtual_frame, orient='vertical',
                                       command=self.virtuals.yview)
        virtual_scroll.grid(row=0, column=1, sticky='ns')
        self.virtuals.configure(yscrollcommand=virtual_scroll.set)

        virtual_buttons = ttk.Frame(virtual_frame)
        virtual_buttons.grid(row=1, column=0, columnspan=2, sticky='ew',
                             pady=(8, 0))
        ttk.Button(virtual_buttons, text='Montuj plik',
                   command=self._mount_virtual_file).pack(side='left')
        ttk.Button(virtual_buttons, text='Pusty dysk',
                   command=self._mount_virtual_empty).pack(side='left',
                                                           padx=(6, 0))
        if self.SHOW_EXPERIMENTAL_ATR_CREATOR:
            ttk.Button(virtual_buttons, text='Nowy ATR',
                       command=self._create_atr_virtual).pack(side='left',
                                                              padx=(6, 0))
        ttk.Button(virtual_buttons, text='Odmontuj',
                   command=self._unmount_virtual).pack(side='left',
                                                       padx=(6, 0))

        log_frame = ttk.LabelFrame(log_tab, text='Log', padding=8)
        log_frame.grid(row=0, column=0, sticky='nsew')
        log_frame.rowconfigure(1, weight=1)
        log_frame.columnconfigure(0, weight=1)

        log_controls = ttk.Frame(log_frame)
        log_controls.grid(row=0, column=0, columnspan=2, sticky='ew',
                          pady=(0, 8))
        ttk.Checkbutton(log_controls, text='Log SIO',
                        variable=self.verbose).pack(side='left')
        ttk.Button(log_controls, text='Wyczysc log',
                   command=self._clear_log).pack(side='right')

        self.log_text = tk.Text(log_frame, height=8, wrap='word',
                                state='disabled')
        self.log_text.grid(row=1, column=0, sticky='nsew')
        log_scroll = ttk.Scrollbar(log_frame, orient='vertical',
                                   command=self.log_text.yview)
        log_scroll.grid(row=1, column=1, sticky='ns')
        self.log_text.configure(yscrollcommand=log_scroll.set)

    # --------------------------------------------------------------- helpers

    def _add_status_led(self, parent, name, color):
        item = ttk.Frame(parent)
        item.pack(side='left', padx=(0, 10))
        lamp = tk.Canvas(item, width=18, height=18,
                         bg=self.cget('bg'), highlightthickness=0, bd=0)
        lamp.pack(side='left')
        ttk.Label(item, text=name).pack(side='left', padx=(3, 0))
        self.status_led_canvases[name] = (lamp, color)
        self._draw_status_led(name, False)

    def _draw_led_canvas(self, canvas, color, name, active):
        canvas.delete('all')
        off_fill = '#341616' if name != 'SDACT' else '#12331a'
        fill = color if active else off_fill
        if active and name != 'SDACT':
            outline = '#ff6b6b'
        elif active:
            outline = '#68e886'
        else:
            outline = '#333333'
        canvas.create_oval(3, 3, 15, 15, fill=fill, outline=outline, width=1)
        if active:
            canvas.create_oval(6, 5, 9, 8, fill='#ffdede', outline='')

