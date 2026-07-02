// ═══════════════════════════════════════════════════════
//  Paramétrage — Module JS (données mockées, zéro backend)
//  Formulaire hiérarchique : Campus > Filière > UE > Module > Profs
// ═══════════════════════════════════════════════════════

const Parametrage = {
    container: null,

    campusList: [],
    allPrograms: [],
    teachersList: [],
    templatesList: [],
    mockUEsByProgram: {},

    // ─── État courant ───────────────────────────────────
    programsList: [],
    selectedCampusId: null,
    selectedProgramId: null,
    selectedTemplateId: null,
    semesterYear: '',
    schoolYear: [],
    selectedSchoolYear: '',
    ues: [],
    nextId: 9000,
    isLoading: false,
    loadError: null,
    importedFile: null,     // Fichier .xlsx sélectionné (pas encore envoyé)
    _notifTimer: null,      // Timer pour auto-dismiss de la notification
    isProgramManager: false,           // True si l'utilisateur est RP-RM (pas de création de filière)

    // ─── Init ───────────────────────────────────────────
    init(containerId, initialData = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) return;

        console.log(initialData);

        this.templatesList = (initialData.templates || []).map(template => ({
            id: template.template_id,
            titre: template.name
        }));
        this.campusList = initialData.campusList || [];
        this.allPrograms = initialData.programs || [];
        this.teachersList = initialData.teachersList || [];
        console.log(this.teachersList);
        this.mockUEsByProgram = initialData.uesByFiliere || {};
        this.selectedCampusId = initialData.selectedCampusId || null;
        this.selectedProgramId = initialData.selectedProgramId || null;
        this.selectedTemplateId = initialData.selectedTemplateId || null;
        this.semesterYear = initialData.semesterYear || '';
        this.schoolYears = initialData.schoolYears || [];
        
        this.selectedSchoolYear = initialData.selectedSchoolYear || '';
        this.isProgramManager = initialData.isProgramManager || false;
        // Pour les RP-RM, afficher toutes les filières autorisées sans filtrage par campus
        if (this.isProgramManager) {
            this.programsList = this.allPrograms;
        } else {
            this.programsList = this.selectedCampusId ? this.allPrograms.filter(f => f.campus_id === this.selectedCampusId) : [];
        }

        this.render();

        // Au chargement initial : charger les modules de l'année précédente
        // si les 3 valeurs (semestre, formation, année) sont déjà renseignées
        this._tryFetchModulesPrecedents();
    },

    // ─── Render principal ───────────────────────────────
    render() {
        this.container.innerHTML = `
            <div class="pub-header">
                <div class="pub-field">
                    <label>Modèle de questions</label>
                    <select id="param-template" onchange="Parametrage.selectedTemplateId = parseInt(this.value) || null;">
                        ${this.templatesList.map(t => `<option value="${t.id}" ${this.selectedTemplateId === t.id ? 'selected' : ''}>${t.titre}</option>`).join('')}
                    </select>
                </div>
                <div class="pub-field">
                    <label>Semestre</label>
                    <select id="param-semestre" onchange="Parametrage.onSemestreChange(this.value)">
                        <option value="">-- Sélectionnez un semestre --</option>
                        ${['Automne','Printemps'].map(s => `<option value="${s}" ${this.semesterYear === s ? 'selected' : ''}>${s}</option>`).join('')}
                    </select>
                </div>
                <div class="pub-field">
                    <label>Année scolaire</label>
                    <div class="param-select-group" style="display: flex; gap: 10px; width: 100%;">
                        <select id="param-annee" onchange="Parametrage.onAnneeChange(this.value)" style="flex: 1;">
                            <option value="">-- Sélectionnez -- </option>
                            ${this.schoolYears.map(a => `<option value="${a}" ${this.selectedSchoolYear === a ? 'selected' : ''}>${a}</option>`).join('')}
                        </select>
                        <button class="btn-icon" onclick="Parametrage.addAnneeScolaire()" title="Ajouter une année scolaire" style="flex-shrink: 0; padding: 0 15px; background: linear-gradient(135deg, #1a5276, #1f6f9f); color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: bold;">+</button>
                    </div>
                </div>
            </div>

            <hr style="border:0; border-top:1px solid #e0e6ec; margin:20px 0;">

            <div class="param-selectors">
                <div class="param-field">
                    <label>Campus</label>
                    <div class="param-select-group">
                        <select id="param-campus" onchange="Parametrage.onCampusChange()">
                            <option value="">-- Sélectionnez un campus --</option>
                            ${this.campusList.map(c => `<option value="${c.id}" ${this.selectedCampusId === c.id ? 'selected' : ''}>${c.name}</option>`).join('')}
                        </select>
                    </div>
                </div>
                <div class="param-field">
                    <label>Filière</label>
                    <div class="param-select-group">
                        <select id="param-filiere" onchange="Parametrage.onFiliereChange()" ${!this.isProgramManager && !this.selectedCampusId ? 'disabled' : ''}>
                            <option value="">-- Sélectionnez une filière --</option>
                            ${this.programsList.map(f => `<option value="${f.id}" ${this.selectedProgramId === f.id ? 'selected' : ''}>${f.name}</option>`).join('')}
                        </select>
                    </div>
                </div>
            </div>
            
            <div id="param-ue-container"></div>

            <div class="dropzone-section">
                <h3>📋 Importer la liste des étudiants</h3>
                <div class="dropzone" id="dropzone-etudiants">
                    <input type="file" id="dropzone-file-input" accept=".xlsx">
                    ${this.importedFile ? `
                        <span class="dropzone__icon">✅</span>
                        <div class="dropzone__text">Fichier prêt à envoyer</div>
                        <div class="dropzone__file-info">
                            <span>📄 ${this.esc(this.importedFile.name)}</span>
                            <button class="file-remove" onclick="event.stopPropagation(); Parametrage.removeFile();" title="Retirer le fichier">&times;</button>
                        </div>
                    ` : `
                        <span class="dropzone__icon">📥</span>
                        <div class="dropzone__text">
                            <strong>Glissez-déposez</strong> votre fichier Excel ici<br>
                            ou <strong>cliquez</strong> pour sélectionner
                            <small>Format accepté : .xlsx uniquement</small>
                        </div>
                    `}
                </div>
            </div>

            <button class="btn-publish" onclick="Parametrage.publish()" ${!this.selectedProgramId ? 'disabled' : ''}>Publier le sondage</button>
        `;

        this.renderUEContainer();
        this.bindDropzone();
    },

    // ─── Semestre change ─────────────────────────────────
    onSemestreChange(value) {
        this.semesterYear = value;
        this._tryFetchModulesPrecedents();
    },

    // ─── Année scolaire change ───────────────────────────
    onAnneeChange(value) {
        this.selectedSchoolYear = value;
        this._tryFetchModulesPrecedents();
    },

    // ─── Campus change ──────────────────────────────────
    async onCampusChange() {
        const sel = document.getElementById('param-campus');
        this.selectedCampusId = sel.value ? parseInt(sel.value) : null;
        this.selectedProgramId = null;

        if (this.isProgramManager) {
            // RP-RM : toujours afficher toutes les filières autorisées
            this.programsList = this.allPrograms;
        } else if (this.selectedCampusId) {
            this.programsList = this.allPrograms.filter(f => f.campus_id === this.selectedCampusId);
        } else {
            this.programsList = [];
        }
        this.render();
        await this.fetchAndUpdateData();
    },

    renderUEContainer() {
        const container = document.getElementById('param-ue-container');
        if (!container) return;

        if (this.loadError) {
            container.innerHTML = `<p class="param-empty">${this.esc(this.loadError)}</p>`;
            return;
        }

        if (this.isLoading && !this.selectedProgramId) {
            container.innerHTML = `<p class="param-empty">Chargement des filières...</p>`;
            return;
        }

        if (!this.selectedProgramId) {
            if (this.isProgramManager) {
                container.innerHTML = `<p class="param-empty">Sélectionnez une filière pour configurer les cours et professeurs.</p>`;
            } else if (!this.selectedCampusId) {
                container.innerHTML = `<p class="param-empty">Sélectionnez un campus et une filière pour configurer les cours et professeurs.</p>`;
            } else if (this.programsList.length === 0) {
                container.innerHTML = `<p class="param-empty">Aucune filière disponible pour ce campus.</p>`;
            } else {
                container.innerHTML = `<p class="param-empty">Sélectionnez une filière pour configurer les cours et professeurs.</p>`;
            }
            return;
        }

        if (this.selectedProgramId) {
            this.renderUEs();
            return;
        }

        container.innerHTML = '';
    },

    async fetchAndUpdateData() {
        if (!window.fetch) return;

        this.isLoading = true;
        this.loadError = null;
        this.renderUEContainer();

        try {
            const response = await fetch('/api/parametrage', { cache: 'no-store' });
            if (!response.ok) {
                throw new Error(`Impossible de charger les données : ${response.status}`);
            }
            const data = await response.json();

            console.log(data);

            this.campusList = data.campusList || this.campusList;
            this.allPrograms = data.programs || this.allPrograms;
            this.teachersList = data.teachersList || this.teachersList;
            console.log(this.teachersList);
            this.templatesList = (data.templates || []).map(template => ({
                id: template.template_id,
                titre: template.name
            }));
            this.mockUEsByProgram = data.uesByFiliere || this.mockUEsByProgram;
            if (data.schoolYears) this.schoolYears = data.schoolYears;
            if (data.selectedSchoolYear && !this.selectedSchoolYear) this.selectedSchoolYear = data.selectedSchoolYear;

            if (this.isProgramManager) {
                // RP-RM : toujours afficher toutes les filières autorisées
                this.programsList = this.allPrograms;
            } else if (this.selectedCampusId) {
                this.programsList = this.allPrograms.filter(f => f.campus_id === this.selectedCampusId);
            } else {
                this.programsList = [];
            }

            if (this.selectedProgramId) {
                this.ues = JSON.parse(JSON.stringify(this.mockUEsByProgram[this.selectedProgramId] || []));
            }
        } catch (error) {
            this.loadError = error.message || 'Une erreur est survenue pendant le chargement.';
        } finally {
            this.isLoading = false;
            this.render();
        }
    },



    // ─── Filière change ─────────────────────────────────
    async onFiliereChange() {
        const sel = document.getElementById('param-filiere');
        this.selectedProgramId = sel.value ? parseInt(sel.value) : null;
        this.ues = [];
        this.render();
        // Charger les modules de l'année précédente pour cette nouvelle filière
        await this._tryFetchModulesPrecedents();
    },



    addAnneeScolaire() {
        const nouvelleAnnee = prompt("Saisissez la nouvelle année scolaire (ex: 2024-2025) :");
        if (!nouvelleAnnee || !nouvelleAnnee.trim()) return;
        const school_year = nouvelleAnnee.trim();
        if (!this.schoolYears.includes(school_year)) {
            this.schoolYears.push(school_year);
        }
        this.selectedSchoolYear = school_year;
        this.render();
        this._tryFetchModulesPrecedents();
    },

    // ─── Chargement des modules de l'année précédente ───
    async _tryFetchModulesPrecedents() {
        // Résoudre le nom de la filière sélectionnée
        const filiereNom = this.selectedProgramId
            ? (this.allPrograms.find(f => f.id === this.selectedProgramId) ||
               this.programsList.find(f => f.id === this.selectedProgramId))?.name || ''
            : '';

        // On ne peut lancer la requête que si les 3 valeurs sont renseignées
        if (!this.semesterYear || !filiereNom || !this.selectedSchoolYear) {
            return;
        }

        this.isLoading = true;
        this.loadError = null;
        this.renderUEContainer();

        try {
            const params = new URLSearchParams({
                semester: this.semesterYear,
                program: filiereNom,
                school_year: this.selectedSchoolYear,
            });
            const response = await fetch(`/api/modules/previous?${params}`, {
                cache: 'no-store',
            });
            if (!response.ok) {
                throw new Error(`Erreur serveur : ${response.status}`);
            }
            const data = await response.json();

            if (data.ues && data.ues.length > 0) {
                // Réassigner des IDs locaux pour éviter les conflits
                let localId = this.nextId;
                this.ues = data.ues.map(ue => {
                    localId++;
                    return {
                        ...ue,
                        id: localId,
                        _open: true,
                        modules: (ue.modules || []).map(mod => {
                            localId++;
                            return { ...mod, id: localId };
                        }),
                    };
                });
                this.nextId = localId;

                console.log(data.teachersList)

                // Enrichir la liste des profs avec ceux du sondage précédent
                if (data.teachersList && data.teachersList.length > 0) {
                    const existingIds = new Set(this.teachersList.map(p => `${(p.firstname||'').toLowerCase()}_${(p.name||'').toLowerCase()}`));
                    for (const teacher of data.teachersList) {
                        const key = `${(teacher.firstname||'').toLowerCase()}_${(teacher.name||'').toLowerCase()}`;
                        if (!existingIds.has(key)) {
                            this.nextId++;
                            teacher.id = this.nextId;
                            this.teachersList.push(teacher);
                            existingIds.add(key);
                        }
                    }
                }

                console.log(`[Parametrage] ${data.ues.length} UE(s) chargée(s) depuis le sondage ${data.previousSchoolYear}`);
            } else {
                // Aucun historique : liste vide, l'utilisateur ajoutera manuellement
                this.ues = [];
                console.log('[Parametrage] Aucun sondage précédent trouvé, liste vide.');
            }
        } catch (error) {
            console.error('[Parametrage] Erreur chargement modules précédents:', error);
            this.ues = [];
            // Pas de loadError bloquant : on laisse l'utilisateur ajouter manuellement
        } finally {
            this.isLoading = false;
            this.render();
        }
    },

    // ─── Render la liste des UE ─────────────────────────
    renderUEs() {
        const container = document.getElementById('param-ue-container');
        if (!container) return;

        if (this.isLoading) {
            container.innerHTML = `
                <p class="param-empty">Chargement des données pour la filière...</p>
            `;
            return;
        }

        if (this.ues.length === 0) {
            container.innerHTML = `
                <p class="param-empty">Aucune UE pour cette filière.</p>
                <button class="param-btn-add param-btn-add-ue" onclick="Parametrage.addUE()">+ Ajouter une UE</button>
            `;
            return;
        }

        container.innerHTML = `
            <div class="param-ue-list">
                ${this.ues.map((ue, i) => this.renderUE(ue, i)).join('')}
            </div>
            <button class="param-btn-add param-btn-add-ue" onclick="Parametrage.addUE()">+ Ajouter une UE</button>
        `;
    },

    // ─── Render une UE ──────────────────────────────────
    renderUE(ue, index) {
        const isOpen = ue._open !== false;
        return `
            <div class="param-ue ${isOpen ? 'open' : ''}" data-ue-id="${ue.id}">
                <div class="param-ue-header" onclick="Parametrage.toggleUE(${ue.id})">
                    <span class="param-chevron"></span>
                    <span class="param-ue-name">
                        <input type="text" value="${this.esc(ue.name)}"
                               onclick="event.stopPropagation()"
                               onblur="Parametrage.renameUE(${ue.id}, this.value)"
                               onkeydown="if(event.key==='Enter'){this.blur();}">
                    </span>
                    ${ue.is_optional ? '<span class="param-badge-optionnel">Optionnelle</span>' : ''}
                    <span class="param-ue-actions" onclick="event.stopPropagation()">
                        <label><input type="checkbox" ${ue.is_optional ? 'checked' : ''} onchange="Parametrage.toggleOptional(${ue.id}, this.checked)"> Opt.</label>
                        <button class="param-btn-remove" onclick="Parametrage.removeUE(${ue.id})" title="Supprimer l'UE">&times;</button>
                    </span>
                </div>
                <div class="param-ue-body">
                    <div class="param-module-list">
                        ${(ue.modules || []).map(m => this.renderModule(m, ue.id)).join('')}
                    </div>
                    <button class="param-btn-add" onclick="Parametrage.addModule(${ue.id})">+ Ajouter un module</button>
                </div>
            </div>
        `;
    },

    // ─── Render un Module ───────────────────────────────
    renderModule(mod, ueId) {
        const assignedIds = (mod.teachers || []).map(p => p.id);
        const availableProfs = this.teachersList.filter(p => !assignedIds.includes(p.id));

        return `
            <div class="param-module" data-module-id="${mod.id}">
                <div class="param-module-name">
                    <input type="text" value="${this.esc(mod.name)}" placeholder="Nom du module"
                           onblur="Parametrage.renameModule(${mod.id}, this.value, ${ueId})"
                           onkeydown="if(event.key==='Enter'){this.blur();}">
                </div>
                <div class="param-module-modalite">
                    <label class="param-checkbox-label">
                        <input type="checkbox" ${mod.one_teacher_in_list ? 'checked' : ''}
                               onchange="Parametrage.toggleChoixEnseignant(${mod.id}, this.checked, ${ueId})">
                        <span>1 seul enseignant parmi la liste</span>
                    </label>
                </div>
                <div class="param-module-profs">
                    <ul class="param-prof-list">
                        ${(mod.teachers || []).map(p => `
                            <li class="param-prof-item">
                                <span class="param-prof-name">${this.esc(p.firstname)} ${this.esc(p.name)}</span>
                                <button class="param-remove-tag" onclick="Parametrage.removeProf(${mod.id}, ${p.id}, ${ueId})">&times;</button>
                            </li>
                        `).join('')}
                    </ul>
                    <span class="param-prof-dropdown">
                        <button class="param-add-prof-btn" onclick="Parametrage.toggleProfDropdown(${mod.id})">+ Prof</button>
                        <div class="param-prof-dropdown-content" id="prof-dd-${mod.id}">
                            <div class="param-prof-option param-prof-option-new" onclick="Parametrage.createNewProf(${mod.id}, ${ueId})">
                                + Créer un nouveau professeur
                            </div>
                            ${availableProfs.length === 0 ? '<div class="param-prof-option" style="color:#999;">Aucun prof disponible</div>' :
                availableProfs.map(p => `
                                <div class="param-prof-option" onclick="Parametrage.addProf(${mod.id}, ${p.id}, ${ueId})">
                                    ${this.esc(p.firstname)} ${this.esc(p.name)}
                                </div>
                              `).join('')}
                        </div>
                    </span>
                </div>
                <button class="param-btn-remove" onclick="Parametrage.removeModule(${mod.id}, ${ueId})" title="Supprimer le module">&times;</button>
            </div>
        `;
    },

    // ─── Actions UE ─────────────────────────────────────
    toggleUE(ueId) {
        const ue = this.ues.find(u => u.id === ueId);
        if (ue) {
            ue._open = ue._open === false ? true : false;
            this.renderUEs();
        }
    },

    addUE() {
        if (!this.selectedProgramId) return;
        const nom = prompt('Nom de la nouvelle UE :');
        if (!nom || !nom.trim()) return;
        const newId = ++this.nextId;
        this.ues.push({
            id: newId,
            name: nom.trim(),
            filiere_id: this.selectedProgramId,
            is_optional: false,
            _open: true,
            modules: []
        });
        this.renderUEs();
    },

    renameUE(ueId, newName) {
        if (!newName || !newName.trim()) return;
        const ue = this.ues.find(u => u.id === ueId);
        if (ue) ue.name = newName.trim();
    },

    toggleOptional(ueId, checked) {
        const ue = this.ues.find(u => u.id === ueId);
        if (ue) {
            ue.is_optional = checked;
            this.renderUEs();
        }
    },

    removeUE(ueId) {
        if (!confirm('Supprimer cette UE et tous ses modules ?')) return;
        this.ues = this.ues.filter(u => u.id !== ueId);
        this.renderUEs();
    },

    // ─── Actions Module ─────────────────────────────────
    addModule(ueId) {
        const ue = this.ues.find(u => u.id === ueId);
        if (!ue) return;
        const newId = ++this.nextId;
        if (!ue.modules) ue.modules = [];
        ue.modules.push({
            id: newId,
            name: 'Nouveau module',
            ue_id: ueId,
            one_teacher_in_list: false,
            teachers: []
        });
        ue._open = true;
        this.renderUEs();
    },

    renameModule(modId, newName, ueId) {
        if (!newName || !newName.trim()) return;
        const ue = this.ues.find(u => u.id === ueId);
        if (!ue) return;
        const mod = (ue.modules || []).find(m => m.id === modId);
        if (mod) mod.name = newName.trim();
    },

    toggleChoixEnseignant(modId, checked, ueId) {
        const ue = this.ues.find(u => u.id === ueId);
        if (!ue) return;
        const mod = (ue.modules || []).find(m => m.id === modId);
        if (mod) mod.one_teacher_in_list = checked;
    },

    removeModule(modId, ueId) {
        if (!confirm('Supprimer ce module ?')) return;
        const ue = this.ues.find(u => u.id === ueId);
        if (!ue) return;
        ue.modules = (ue.modules || []).filter(m => m.id !== modId);
        ue._open = true;
        this.renderUEs();
    },

    // ─── Actions Professeur ─────────────────────────────
    toggleProfDropdown(modId) {
        document.querySelectorAll('.param-prof-dropdown-content.show').forEach(el => {
            if (el.id !== 'prof-dd-' + modId) el.classList.remove('show');
        });
        const dd = document.getElementById('prof-dd-' + modId);
        if (dd) dd.classList.toggle('show');
    },

    addProf(modId, teacherId, ueId) {
        const dd = document.getElementById('prof-dd-' + modId);
        if (dd) dd.classList.remove('show');

        const ue = this.ues.find(u => u.id === ueId);
        if (!ue) return;
        const mod = (ue.modules || []).find(m => m.id === modId);
        if (!mod) return;

        const teacher = this.teachersList.find(p => p.id === teacherId);
        if (!teacher) return;
        if (!mod.teachers) mod.teachers = [];
        mod.teachers.push({ ...teacher });
        ue._open = true;
        this.renderUEs();
    },

    createNewProf(modId, ueId) {
        const dd = document.getElementById('prof-dd-' + modId);
        if (dd) dd.classList.remove('show');

        const firstname = prompt('Prénom du professeur :');
        if (!firstname || !firstname.trim()) return;
        const nom = prompt('Nom du professeur :');
        if (!nom || !nom.trim()) return;

        const newId = ++this.nextId;
        const newProf = { id: newId, name: nom.trim(), firstname: firstname.trim() };
        this.teachersList.push(newProf);
        this.addProf(modId, newId, ueId);
    },

    removeProf(modId, teacherId, ueId) {
        const ue = this.ues.find(u => u.id === ueId);
        if (!ue) return;
        const mod = (ue.modules || []).find(m => m.id === modId);
        if (!mod) return;
        mod.teachers = (mod.teachers || []).filter(p => p.id !== teacherId);
        ue._open = true;
        this.renderUEs();
    },

    // ─── Drag & Drop : liaisons événements ────────────────
    bindDropzone() {
        const dropzone = document.getElementById('dropzone-etudiants');
        const fileInput = document.getElementById('dropzone-file-input');
        if (!dropzone || !fileInput) return;

        // Empêcher le clic sur l'input de remonter au dropzone (cause du double-open)
        fileInput.addEventListener('click', (e) => e.stopPropagation());

        // Clic sur la zone → ouvrir le sélecteur de fichier
        dropzone.addEventListener('click', (e) => {
            // Ne pas re-déclencher si le clic vient déjà de l'input
            if (e.target === fileInput) return;
            fileInput.click();
        });

        // Sélection via l'input
        fileInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files[0]) {
                this.handleFile(e.target.files[0]);
            }
        });

        // Drag events
        dropzone.addEventListener('dragenter', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add('dropzone--dragover');
        });

        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add('dropzone--dragover');
        });

        dropzone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('dropzone--dragover');
        });

        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('dropzone--dragover');
            if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                this.handleFile(e.dataTransfer.files[0]);
            }
        });
    },

    // ─── Fichier : validation et stockage ────────────────
    handleFile(file) {
        if (!file.name.toLowerCase().endsWith('.xlsx')) {
            this.showNotification('Format invalide. Seuls les fichiers .xlsx sont acceptés.', 'error');
            return;
        }
        this.importedFile = file;
        this.render();
        this.showNotification(`Fichier "${file.name}" prêt pour l'import.`, 'info');
    },

    removeFile() {
        this.importedFile = null;
        this.render();
    },

    // ─── Notification (banner en bas de l'écran) ─────────
    showNotification(message, type = 'info') {
        // Supprimer l'ancienne notification si présente
        const existing = document.getElementById('import-notification');
        if (existing) existing.remove();
        if (this._notifTimer) clearTimeout(this._notifTimer);

        const icons = { success: '✅', error: '❌', info: 'ℹ️' };
        const el = document.createElement('div');
        el.id = 'import-notification';
        el.className = `import-notification import-notification--${type}`;
        el.innerHTML = `
            <span class="import-notification__icon">${icons[type] || icons.info}</span>
            <span>${message}</span>
            <button class="import-notification__close" onclick="this.parentElement.classList.remove('show'); setTimeout(() => this.parentElement.remove(), 400);">&times;</button>
        `;
        document.body.appendChild(el);

        // Trigger l'animation
        requestAnimationFrame(() => el.classList.add('show'));

        // Auto-dismiss après 6 secondes
        this._notifTimer = setTimeout(() => {
            el.classList.remove('show');
            setTimeout(() => el.remove(), 400);
        }, 6000);
    },

    // ─── Publication (atomique : sondage + import en une seule requête) ──
    async publish() {
        if (!this.selectedTemplateId) {
            this.selectedTemplateId = this.templatesList[0]?.id;
        }
        if (!this.selectedCampusId) return alert('Veuillez sélectionner un Campus.');
        if (!this.selectedProgramId) return alert('Veuillez sélectionner une Filière.');
        if (!this.semesterYear || !this.semesterYear.trim()) return alert("Veuillez sélectionner un semestre.");
        if (!this.selectedSchoolYear || !this.selectedSchoolYear.trim()) return alert("Veuillez sélectionner une année scolaire.");
        if (this.ues.length === 0) return alert('Le sondage doit contenir au moins une UE.');
        if (!this.importedFile) return alert('Veuillez importer la liste des étudiants (fichier .xlsx) avant de publier.');

        const campusNom = this.campusList.find(c => c.id === this.selectedCampusId)?.name || '';
        const filiereNom = this.programsList.find(f => f.id === this.selectedProgramId)?.name || '';

        // Préparer les données du sondage en JSON
        const surveyData = {
            template_id: this.selectedTemplateId,
            campus: campusNom,
            program: filiereNom,
            semester: this.semesterYear,
            school_year: this.selectedSchoolYear,
            ues: this.ues.map(ue => ({
                id: ue.id,
                name: ue.name,
                is_optional: ue.is_optional,
                modules: (ue.modules || []).map(mod => ({
                    id: mod.id,
                    name: mod.name,
                    one_teacher_in_list: mod.one_teacher_in_list || false,
                    teachers: (mod.teachers || []).map(teacher => ({
                        id: teacher.id,
                        firstname: teacher.firstname,
                        name: teacher.name
                    }))
                }))
            }))
        };

        // Désactiver le bouton pendant le traitement
        const btn = document.querySelector('.btn-publish');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Publication en cours...';
        }

        // Construire le FormData avec le JSON + fichier optionnel
        const formData = new FormData();
        formData.append('survey_data', JSON.stringify(surveyData));
        if (this.importedFile) {
            formData.append('file', this.importedFile);
        }

        try {
            const response = await fetch('/api/surveys', {
                method: 'POST',
                body: formData,
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.error || `Erreur serveur (${response.status})`);
            }

            // Succès — construire le message
            if (result.nb_emails_lus) {
                this.showNotification(
                    `Sondage publié ! ${result.nb_emails_lus} étudiant(s) traité(s) — ` +
                    `${result.nb_users_crees} nouveau(x), ${result.nb_repondre_inseres} assigné(s).`,
                    'success'
                );
            } else {
                this.showNotification('Sondage publié avec succès !', 'success');
            }

            // Attendre un peu pour lire la notification, puis rediriger
            const questionnaire_url = result.questionnaire_url;
            setTimeout(() => {
                window.location.href = questionnaire_url;
            }, 2500);

        } catch (error) {
            this.showNotification(
                'Erreur lors de la création du sondage : ' + error.message,
                'error'
            );
            console.error(error);
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Publier le sondage';
            }
        }
    },

    // ─── Utils ──────────────────────────────────────────
    esc(str) {
        const div = document.createElement('div');
        div.textContent = str || '';
        return div.innerHTML;
    }
};

// Fermer les dropdowns profs au clic extérieur
document.addEventListener('click', function (e) {
    if (!e.target.closest('.param-prof-dropdown')) {
        document.querySelectorAll('.param-prof-dropdown-content.show').forEach(el => el.classList.remove('show'));
    }
});
