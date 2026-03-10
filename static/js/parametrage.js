// ═══════════════════════════════════════════════════════
//  Paramétrage — Module JS (données mockées, zéro backend)
//  Formulaire hiérarchique : Campus > Filière > UE > Module > Profs
// ═══════════════════════════════════════════════════════

const Parametrage = {
    container: null,

    // ─── Données mockées ──────────────────────────────────
    campusList: [
        { id: 1, nom: 'Campus Paris-Cachan' },
        { id: 2, nom: 'Campus Troyes' },
        { id: 3, nom: 'Campus Montpellier' }
    ],

    allFilieres: [
        { id: 1, nom: 'Ingénierie Numérique', campus_id: 1 },
        { id: 2, nom: 'Mécanique & Énergétique', campus_id: 1 },
        { id: 3, nom: 'Data & IA', campus_id: 2 },
        { id: 4, nom: 'Génie Civil', campus_id: 2 },
        { id: 5, nom: 'Biotechnologies', campus_id: 3 }
    ],

    profsList: [
        { id: 1, nom: 'Dupont', prenom: 'Marie' },
        { id: 2, nom: 'Martin', prenom: 'Jean' },
        { id: 3, nom: 'Bernard', prenom: 'Sophie' },
        { id: 4, nom: 'Leroy', prenom: 'Thomas' },
        { id: 5, nom: 'Moreau', prenom: 'Claire' },
        { id: 6, nom: 'Garcia', prenom: 'Luca' }
    ],

    templatesList: [
        { id: 1, titre: 'Template 2025' }
    ],

    mockUEsByFiliere: {
        1: [
            {
                id: 101, nom: 'Algorithmique', filiere_id: 1, optionnel: false, _open: true,
                modules: [
                    { id: 1001, nom: 'Structures de données', ue_id: 101, modalite: 'OBLIGATOIRE', professeurs: [{ id: 1, nom: 'Dupont', prenom: 'Marie' }] },
                    { id: 1002, nom: 'Complexité algorithmique', ue_id: 101, modalite: 'OBLIGATOIRE', professeurs: [{ id: 2, nom: 'Martin', prenom: 'Jean' }] }
                ]
            },
            {
                id: 102, nom: 'Développement Web', filiere_id: 1, optionnel: true, _open: false,
                modules: [
                    { id: 1003, nom: 'Frontend (HTML/CSS/JS)', ue_id: 102, modalite: 'OBLIGATOIRE', professeurs: [{ id: 3, nom: 'Bernard', prenom: 'Sophie' }] },
                    { id: 1004, nom: 'Backend (Python/Flask)', ue_id: 102, modalite: 'CHOIX_ENSEIGNANT_INCLUSIF', professeurs: [{ id: 4, nom: 'Leroy', prenom: 'Thomas' }, { id: 5, nom: 'Moreau', prenom: 'Claire' }] }
                ]
            },
            {
                id: 103, nom: 'Réseaux & Sécurité', filiere_id: 1, optionnel: false, _open: false,
                modules: [
                    { id: 1005, nom: 'TCP/IP & Protocoles', ue_id: 103, modalite: 'OBLIGATOIRE', professeurs: [{ id: 6, nom: 'Garcia', prenom: 'Luca' }] }
                ]
            }
        ],
        2: [
            {
                id: 201, nom: 'Thermodynamique', filiere_id: 2, optionnel: false, _open: true,
                modules: [
                    { id: 2001, nom: 'Machines thermiques', ue_id: 201, modalite: 'OBLIGATOIRE', professeurs: [{ id: 2, nom: 'Martin', prenom: 'Jean' }] }
                ]
            }
        ],
        3: [
            {
                id: 301, nom: 'Machine Learning', filiere_id: 3, optionnel: false, _open: true,
                modules: [
                    { id: 3001, nom: 'Supervised Learning', ue_id: 301, modalite: 'OBLIGATOIRE', professeurs: [{ id: 1, nom: 'Dupont', prenom: 'Marie' }, { id: 5, nom: 'Moreau', prenom: 'Claire' }] },
                    { id: 3002, nom: 'Deep Learning', ue_id: 301, modalite: 'CHOIX_ENSEIGNANT_EXCLUSIF', professeurs: [{ id: 3, nom: 'Bernard', prenom: 'Sophie' }] }
                ]
            }
        ]
    },

    // ─── État courant ───────────────────────────────────
    filieresList: [],
    selectedCampusId: null,
    selectedFiliereId: null,
    selectedTemplateId: null,
    semestreAnnee: '',
    ues: [],
    nextId: 9000,

    // ─── Init ───────────────────────────────────────────
    init(containerId) {
        this.container = document.getElementById(containerId);
        if (!this.container) return;
        this.render();
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
                    <label>Semestre / Année</label>
                    <input type="text" id="param-semestre" value="${this.semestreAnnee}" onchange="Parametrage.semestreAnnee = this.value;" placeholder="automne/2025">
                </div>
            </div>

            <hr style="border:0; border-top:1px solid #e0e6ec; margin:20px 0;">

            <div class="param-selectors">
                <div class="param-field">
                    <label>Campus</label>
                    <div class="param-select-group">
                        <select id="param-campus" onchange="Parametrage.onCampusChange()">
                            ${this.campusList.map(c => `<option value="${c.id}" ${this.selectedCampusId === c.id ? 'selected' : ''}>${c.nom}</option>`).join('')}
                        </select>
                        <button class="btn-icon" onclick="Parametrage.addCampus()" title="Créer un nouveau campus">+</button>
                    </div>
                </div>
                <div class="param-field">
                    <label>Filière</label>
                    <div class="param-select-group">
                        <select id="param-filiere" onchange="Parametrage.onFiliereChange()" ${!this.selectedCampusId ? 'disabled' : ''}>
                            ${this.filieresList.map(f => `<option value="${f.id}" ${this.selectedFiliereId === f.id ? 'selected' : ''}>${f.nom}</option>`).join('')}
                        </select>
                        <button class="btn-icon" onclick="Parametrage.addFiliere()" title="Créer une nouvelle filière" ${!this.selectedCampusId ? 'disabled style="opacity:0.5;cursor:not-allowed;"' : ''}>+</button>
                    </div>
                </div>
            </div>
            
            <div id="param-ue-container">
                ${this.selectedFiliereId ? '' : '<p class="param-empty">Sélectionnez un campus et une filière pour configurer les cours et professeurs.</p>'}
            </div>

            <button class="btn-publish" onclick="Parametrage.publish()" ${!this.selectedFiliereId ? 'disabled' : ''}>Publier le sondage</button>
        `;

        if (this.selectedFiliereId) {
            this.renderUEs();
        }
    },

    // ─── Campus change ──────────────────────────────────
    onCampusChange() {
        const sel = document.getElementById('param-campus');
        this.selectedCampusId = sel.value ? parseInt(sel.value) : null;
        this.selectedFiliereId = null;
        this.ues = [];

        if (this.selectedCampusId) {
            this.filieresList = this.allFilieres.filter(f => f.campus_id === this.selectedCampusId);
        } else {
            this.filieresList = [];
        }
        this.render();
    },

    addCampus() {
        const nom = prompt('Nom du nouveau campus :');
        if (!nom || !nom.trim()) return;
        const newId = ++this.nextId;
        this.campusList.push({ id: newId, nom: nom.trim() });
        this.selectedCampusId = newId;
        this.selectedFiliereId = null;
        this.ues = [];
        this.filieresList = [];
        this.render();
    },

    // ─── Filière change ─────────────────────────────────
    onFiliereChange() {
        const sel = document.getElementById('param-filiere');
        this.selectedFiliereId = sel.value ? parseInt(sel.value) : null;
        if (this.selectedFiliereId) {
            this.ues = JSON.parse(JSON.stringify(this.mockUEsByFiliere[this.selectedFiliereId] || []));
        } else {
            this.ues = [];
        }
        this.render();
    },

    addFiliere() {
        if (!this.selectedCampusId) return alert("Veuillez d'abord sélectionner ou créer un campus.");
        const nom = prompt('Nom de la nouvelle filière :');
        if (!nom || !nom.trim()) return;
        const newId = ++this.nextId;
        const newFiliere = { id: newId, nom: nom.trim(), campus_id: this.selectedCampusId };
        this.allFilieres.push(newFiliere);
        this.filieresList.push(newFiliere);
        this.selectedFiliereId = newId;
        this.ues = [];
        this.render();
    },

    // ─── Render la liste des UE ─────────────────────────
    renderUEs() {
        const container = document.getElementById('param-ue-container');
        if (!container) return;

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
                        <input type="text" value="${this.esc(ue.nom)}"
                               onclick="event.stopPropagation()"
                               onblur="Parametrage.renameUE(${ue.id}, this.value)"
                               onkeydown="if(event.key==='Enter'){this.blur();}">
                    </span>
                    ${ue.optionnel ? '<span class="param-badge-optionnel">Optionnelle</span>' : ''}
                    <span class="param-ue-actions" onclick="event.stopPropagation()">
                        <label><input type="checkbox" ${ue.optionnel ? 'checked' : ''} onchange="Parametrage.toggleOptional(${ue.id}, this.checked)"> Opt.</label>
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
        const MODALITES = [
            { value: 'OBLIGATOIRE', label: 'Obligatoire' },
            { value: 'CHOIX_ENSEIGNANT_INCLUSIF', label: 'Choix ens. inclusif' },
            { value: 'CHOIX_ENSEIGNANT_EXCLUSIF', label: 'Choix ens. exclusif' }
        ];

        const assignedIds = (mod.professeurs || []).map(p => p.id);
        const availableProfs = this.profsList.filter(p => !assignedIds.includes(p.id));

        return `
            <div class="param-module" data-module-id="${mod.id}">
                <div class="param-module-name">
                    <input type="text" value="${this.esc(mod.nom)}" placeholder="Nom du module"
                           onblur="Parametrage.renameModule(${mod.id}, this.value, ${ueId})"
                           onkeydown="if(event.key==='Enter'){this.blur();}">
                </div>
                <div class="param-module-modalite">
                    <select onchange="Parametrage.changeModalite(${mod.id}, this.value, ${ueId})">
                        ${MODALITES.map(m => `<option value="${m.value}" ${mod.modalite === m.value ? 'selected' : ''}>${m.label}</option>`).join('')}
                    </select>
                </div>
                <div class="param-module-profs">
                    ${(mod.professeurs || []).map(p => `
                        <span class="param-prof-tag">
                            ${this.esc(p.prenom)} ${this.esc(p.nom)}
                            <button class="param-remove-tag" onclick="Parametrage.removeProf(${mod.id}, ${p.id}, ${ueId})">&times;</button>
                        </span>
                    `).join('')}
                    <span class="param-prof-dropdown">
                        <button class="param-add-prof-btn" onclick="Parametrage.toggleProfDropdown(${mod.id})">+ Prof</button>
                        <div class="param-prof-dropdown-content" id="prof-dd-${mod.id}">
                            <div class="param-prof-option param-prof-option-new" onclick="Parametrage.createNewProf(${mod.id}, ${ueId})">
                                + Créer un nouveau professeur
                            </div>
                            ${availableProfs.length === 0 ? '<div class="param-prof-option" style="color:#999;">Aucun prof disponible</div>' :
                availableProfs.map(p => `
                                <div class="param-prof-option" onclick="Parametrage.addProf(${mod.id}, ${p.id}, ${ueId})">
                                    ${this.esc(p.prenom)} ${this.esc(p.nom)}
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
        if (!this.selectedFiliereId) return;
        const nom = prompt('Nom de la nouvelle UE :');
        if (!nom || !nom.trim()) return;
        const newId = ++this.nextId;
        this.ues.push({
            id: newId,
            nom: nom.trim(),
            filiere_id: this.selectedFiliereId,
            optionnel: false,
            _open: true,
            modules: []
        });
        this.renderUEs();
    },

    renameUE(ueId, newName) {
        if (!newName || !newName.trim()) return;
        const ue = this.ues.find(u => u.id === ueId);
        if (ue) ue.nom = newName.trim();
    },

    toggleOptional(ueId, checked) {
        const ue = this.ues.find(u => u.id === ueId);
        if (ue) {
            ue.optionnel = checked;
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
            nom: 'Nouveau module',
            ue_id: ueId,
            modalite: 'OBLIGATOIRE',
            professeurs: []
        });
        ue._open = true;
        this.renderUEs();
    },

    renameModule(modId, newName, ueId) {
        if (!newName || !newName.trim()) return;
        const ue = this.ues.find(u => u.id === ueId);
        if (!ue) return;
        const mod = (ue.modules || []).find(m => m.id === modId);
        if (mod) mod.nom = newName.trim();
    },

    changeModalite(modId, modalite, ueId) {
        const ue = this.ues.find(u => u.id === ueId);
        if (!ue) return;
        const mod = (ue.modules || []).find(m => m.id === modId);
        if (mod) mod.modalite = modalite;
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

    addProf(modId, profId, ueId) {
        const dd = document.getElementById('prof-dd-' + modId);
        if (dd) dd.classList.remove('show');

        const ue = this.ues.find(u => u.id === ueId);
        if (!ue) return;
        const mod = (ue.modules || []).find(m => m.id === modId);
        if (!mod) return;

        const prof = this.profsList.find(p => p.id === profId);
        if (!prof) return;
        if (!mod.professeurs) mod.professeurs = [];
        mod.professeurs.push({ ...prof });
        ue._open = true;
        this.renderUEs();
    },

    createNewProf(modId, ueId) {
        const dd = document.getElementById('prof-dd-' + modId);
        if (dd) dd.classList.remove('show');

        const prenom = prompt('Prénom du professeur :');
        if (!prenom || !prenom.trim()) return;
        const nom = prompt('Nom du professeur :');
        if (!nom || !nom.trim()) return;

        const newId = ++this.nextId;
        const newProf = { id: newId, nom: nom.trim(), prenom: prenom.trim() };
        this.profsList.push(newProf);
        this.addProf(modId, newId, ueId);
    },

    removeProf(modId, profId, ueId) {
        const ue = this.ues.find(u => u.id === ueId);
        if (!ue) return;
        const mod = (ue.modules || []).find(m => m.id === modId);
        if (!mod) return;
        mod.professeurs = (mod.professeurs || []).filter(p => p.id !== profId);
        ue._open = true;
        this.renderUEs();
    },

    // ─── Publication (simulée) ──────────────────────────
    publish() {
        if (!this.selectedTemplateId) {
            this.selectedTemplateId = this.templatesList[0]?.id;
        }
        if (!this.selectedCampusId) return alert('Veuillez sélectionner un Campus.');
        if (!this.selectedFiliereId) return alert('Veuillez sélectionner une Filière.');
        if (!this.semestreAnnee.trim()) return alert("Veuillez saisir le semestre / année.");
        if (this.ues.length === 0) return alert('Le sondage doit contenir au moins une UE.');

        const campusNom = this.campusList.find(c => c.id === this.selectedCampusId)?.nom || '';
        const filiereNom = this.filieresList.find(f => f.id === this.selectedFiliereId)?.nom || '';
        const templateNom = this.templatesList.find(t => t.id === this.selectedTemplateId)?.titre || '';

        this.container.innerHTML = `
            <div style="text-align:center; padding: 40px 20px;">
                <div style="font-size:2.5rem; margin-bottom:20px;">Sondage créé</div>
                <p style="font-size:1rem; color:#3d5a80; margin-bottom:8px; font-weight:600;">
                    ${this.esc(templateNom)}
                </p>
                <p style="font-size:0.95rem; color:#6b7f96; margin-bottom:30px;">
                    ${this.esc(campusNom)} — ${this.esc(filiereNom)} — ${this.esc(this.semestreAnnee)}
                </p>
                <p style="font-size:0.85rem; color:#9aa8b8; margin-bottom:30px;">
                    Mode visuel — la publication réelle nécessite un backend
                </p>
                <a href="/" style="padding:12px 28px; background:linear-gradient(135deg, #1a5276, #1f6f9f); color:white; text-decoration:none; border-radius:6px; font-weight:600;">
                    Retour
                </a>
            </div>
        `;
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
