/* ══════════════════════════════════════════════
   admin.js  –  Gestion des rôles OCEENS II
   ══════════════════════════════════════════════ */

// ── Constantes ──────────────────────────────────
var AVATAR_COLORS = ['#7b2fa0', '#df231d', '#1565c0', '#2e7d32', '#e65100', '#ad1457', '#0277bd', '#558b2f'];

// ── État global ─────────────────────────────────
var currentFilter = 'all';
var searchQuery = '';
var editingUserId = null;
var selectedRole = null;
var selectedFilieres = [];          // filières choisies pour le RP-RM en cours d'édition
var localUsers = ALL_USERS.map(function (u) { return Object.assign({}, u); });

// ── Helpers ─────────────────────────────────────
function parseMail(mail) {
    var parts = mail.split('@')[0].split('.');
    function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase(); }
    return { prenom: cap(parts[0]), nom: parts.length > 1 ? cap(parts[1]) : '' };
}

function getInitials(mail) {
    var p = parseMail(mail);
    return ((p.prenom[0] || '') + (p.nom[0] || '')).toUpperCase();
}

function getRoleBadge(role) {
    if (!role) return '';
    if (role === 'student') return '<span class="role-badge etudiant"><span class="role-dot"></span>Étudiant</span>';
    if (role.startsWith('admin')) {
        var parts = role.split(':');
        var label = parts.length > 1 ? 'Administrateur : ' + parts[1].replace(/;/g, ', ') : 'Administrateur';
        return '<span class="role-badge admin"><span class="role-dot"></span>' + label + '</span>';
    }
    if (role.startsWith('program_manager')) {
        var parts = role.split(':');
        var label = parts.length > 1 ? 'RP-RM : ' + parts[1].replace(/;/g, ', ') : 'RP-RM';
        return '<span class="role-badge rprm"><span class="role-dot"></span>' + label + '</span>';
    }
    return '<span class="role-badge rprm"><span class="role-dot"></span>' + role + '</span>';
}

// Retourne toutes les filières déjà utilisées dans le système
function getAllFilieres() {
    var set = {};
    localUsers.forEach(function (u) {
        if (u.role && (u.role.includes(':'))) {
            var after = u.role.split(':')[1];
            if (after) {
                after.split(';').forEach(function (f) {
                    var t = f.trim();
                    if (t) set[t] = true;
                });
            }
        }
    });
    return Object.keys(set).sort();
}

// ── Filtrage ────────────────────────────────────
function filteredUsers() {
    var q = searchQuery.toLowerCase();
    return localUsers.filter(function (u) {
        var p = parseMail(u.mail);
        var matchSearch = !q || (p.prenom + ' ' + p.nom + ' ' + u.mail).toLowerCase().indexOf(q) !== -1;
        var matchFilter = currentFilter === 'all';
        if (!matchFilter) {
            if (currentFilter === 'program_manager') {
                matchFilter = u.role && u.role.startsWith('program_manager');
            } else if (currentFilter === 'admin') {
                matchFilter = u.role && u.role.startsWith('admin');
            } else {
                matchFilter = u.role === currentFilter;
            }
        }
        return matchSearch && matchFilter;
    });
}

// ── Rendu tableau ────────────────────────────────
function renderTable() {
    var tbody = document.getElementById('users-tbody');
    var empty = document.getElementById('empty-state');
    var table = document.getElementById('users-table');
    var count = document.getElementById('count-label');
    var list = filteredUsers();

    count.textContent = list.length + ' affiché(s)';

    if (!list.length) {
        table.style.display = 'none';
        empty.style.display = 'block';
        return;
    }
    empty.style.display = 'none';
    table.style.display = '';

    tbody.innerHTML = list.map(function (u) {
        var p = parseMail(u.mail);
        return '<tr data-id="' + u.user_id + '">'
            + '<td><div class="user-info">'
            + '<div class="avatar" style="background:' + AVATAR_COLORS[u.user_id % 8] + '">' + getInitials(u.mail) + '</div>'
            + '<div><div class="user-name">' + p.prenom + ' ' + p.nom + '</div>'
            + '<div class="user-email">' + u.mail + '</div></div>'
            + '</div></td>'
            + '<td>' + getRoleBadge(u.role) + '</td>'
            + '<td class="td-actions"><button class="btn-edit" data-id="' + u.user_id + '">Modifier</button></td>'
            + '</tr>';
    }).join('');

    // Clics sur les lignes
    tbody.querySelectorAll('tr').forEach(function (tr) {
        tr.addEventListener('click', function () {
            openModal(parseInt(tr.dataset.id));
        });
    });
}

// ── Section filières : afficher/masquer ─────────
function showFiliereSection() {
    document.getElementById('rprm-formations-section').classList.add('visible');
}
function hideFiliereSection() {
    document.getElementById('rprm-formations-section').classList.remove('visible');
}

// ── Rendu des tags filières ──────────────────────
function renderFiliereTags() {
    var container = document.getElementById('formations-tags');
    if (selectedFilieres.length === 0) {
        container.innerHTML = '<span class="formations-empty-hint">Aucune filière ajoutée</span>';
        return;
    }
    container.innerHTML = selectedFilieres.map(function (f) {
        return '<span class="formation-tag">'
            + f
            + '<button class="formation-tag-remove" data-filiere="' + f + '" title="Retirer">×</button>'
            + '</span>';
    }).join('');

    container.querySelectorAll('.formation-tag-remove').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            var nom = btn.dataset.filiere;
            selectedFilieres = selectedFilieres.filter(function (f) { return f !== nom; });
            renderFiliereTags();
            refreshFiliereDropdown();
        });
    });
}

// ── Rafraîchir le dropdown des filières ─────────
function refreshFiliereDropdown() {
    var select = document.getElementById('formations-select');
    var existing = getAllFilieres();

    select.innerHTML = '<option value="">-- Sélectionner une filière --</option>';

    existing.forEach(function (f) {
        if (selectedFilieres.indexOf(f) === -1) {
            var opt = document.createElement('option');
            opt.value = f;
            opt.textContent = f;
            select.appendChild(opt);
        }
    });

    var newOpt = document.createElement('option');
    newOpt.value = '__new__';
    newOpt.textContent = '+ Créer une nouvelle filière';
    select.appendChild(newOpt);
}

// ── Ouvrir la modale ────────────────────────────
function openModal(userId) {
    var user = localUsers.find(function (u) { return u.user_id === userId; });
    if (!user) return;

    editingUserId = userId;

    // Détecter le rôle et extraire les filières si RP-RM
    if (user.role && (user.role.includes(':'))) {
        var parts = user.role.split(':');
        selectedRole = parts[0];
        selectedFilieres = parts.length > 1
            ? parts[1].split(';').map(function (f) { return f.trim(); }).filter(Boolean)
            : [];
    } else {
        selectedRole = user.role || 'student';
        selectedFilieres = [];
    }

    // Header
    var p = parseMail(user.mail);
    document.getElementById('modal-title').textContent = p.prenom + ' ' + p.nom;
    document.getElementById('modal-subtitle').textContent = user.mail;

    // Surligner le bon bouton de rôle
    document.querySelectorAll('.role-option').forEach(function (el) {
        el.classList.toggle('selected', el.dataset.role === selectedRole);
    });

    // Section filières
    if (selectedRole === 'program_manager' || selectedRole === 'admin') {
        showFiliereSection();
    } else {
        hideFiliereSection();
    }
    renderFiliereTags();
    refreshFiliereDropdown();

    // Cacher le champ "nouvelle filière"
    document.getElementById('new-formation-row').classList.remove('visible');
    document.getElementById('new-formation-input').value = '';

    // Réactiver le bouton save
    var btnSave = document.getElementById('btn-save');
    btnSave.disabled = false;
    btnSave.textContent = 'Enregistrer';

    // Ouvrir
    document.getElementById('modal-overlay').classList.add('open');
}

// ── Fermer la modale ────────────────────────────
function closeModal() {
    document.getElementById('modal-overlay').classList.remove('open');
    document.getElementById('new-formation-row').classList.remove('visible');
    document.getElementById('new-formation-input').value = '';
    editingUserId = null;
    selectedFilieres = [];
}

// ── Sélection du rôle dans la modale ────────────
document.querySelectorAll('.role-option').forEach(function (opt) {
    opt.addEventListener('click', function () {
        document.querySelectorAll('.role-option').forEach(function (o) { o.classList.remove('selected'); });
        opt.classList.add('selected');
        selectedRole = opt.dataset.role;

        if (selectedRole === 'program_manager' || selectedRole === 'admin') {
            showFiliereSection();
            renderFiliereTags();
            refreshFiliereDropdown();
        } else {
            hideFiliereSection();
            selectedFilieres = [];
        }
    });
});

// ── Ajouter une filière depuis le dropdown ───────
document.getElementById('btn-add-formation').addEventListener('click', function () {
    var select = document.getElementById('formations-select');
    var val = select.value;
    if (!val) return;

    if (val === '__new__') {
        document.getElementById('new-formation-row').classList.add('visible');
        document.getElementById('new-formation-input').focus();
        select.value = '';
        return;
    }

    if (selectedFilieres.indexOf(val) === -1) {
        selectedFilieres.push(val);
        renderFiliereTags();
        refreshFiliereDropdown();
    }
    select.value = '';
});

// ── Confirmer une nouvelle filière ───────────────
document.getElementById('btn-confirm-formation').addEventListener('click', function () {
    var input = document.getElementById('new-formation-input');
    var val = input.value.trim();
    if (!val) return;

    if (selectedFilieres.indexOf(val) === -1) {
        selectedFilieres.push(val);
        renderFiliereTags();
        refreshFiliereDropdown();
    }
    input.value = '';
    document.getElementById('new-formation-row').classList.remove('visible');
});

// ── Annuler nouvelle filière ─────────────────────
document.getElementById('btn-cancel-new-formation').addEventListener('click', function () {
    document.getElementById('new-formation-input').value = '';
    document.getElementById('new-formation-row').classList.remove('visible');
});

// ── Clavier sur le champ nouvelle filière ────────
document.getElementById('new-formation-input').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); document.getElementById('btn-confirm-formation').click(); }
    if (e.key === 'Escape') { document.getElementById('btn-cancel-new-formation').click(); }
});

// ── Sauvegarde ───────────────────────────────────
document.getElementById('btn-save').addEventListener('click', function () {
    var user = localUsers.find(function (u) { return u.user_id === editingUserId; });
    if (!user || !selectedRole) return;

    // Construire le rôle final
    var finalRole = selectedRole;
    if (selectedRole === 'program_manager' && selectedFilieres.length > 0) {
        finalRole = 'program_manager:' + selectedFilieres.join(';');
    }
    if (selectedRole === 'admin' && selectedFilieres.length > 0) {
        finalRole = 'admin:' + selectedFilieres.join(';');
    }

    var btn = document.getElementById('btn-save');
    btn.disabled = true;
    btn.textContent = 'Enregistrement…';

    fetch('/api/users/' + editingUserId + '/role', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: finalRole })
    })
        .then(function (resp) {
            if (!resp.ok) {
                return resp.json().catch(function () { return {}; }).then(function (err) {
                    throw new Error(err.detail || 'HTTP ' + resp.status);
                });
            }
            return resp.json();
        })
        .then(function () {
            user.role = finalRole;
            closeModal();
            renderTable();
            var p = parseMail(user.mail);
            showToast('Rôle de ' + p.prenom + ' ' + p.nom + ' mis à jour', 'success');
        })
        .catch(function (err) {
            showToast('Erreur : ' + err.message, 'error');
            btn.disabled = false;
            btn.textContent = 'Enregistrer';
        });
});

// ── Fermeture modale ─────────────────────────────
document.getElementById('btn-cancel').addEventListener('click', closeModal);
document.getElementById('modal-overlay').addEventListener('click', function (e) {
    if (e.target === document.getElementById('modal-overlay')) closeModal();
});

// ── Recherche ────────────────────────────────────
document.getElementById('search-input').addEventListener('input', function (e) {
    searchQuery = e.target.value;
    renderTable();
});

// ── Filtres ──────────────────────────────────────
document.querySelectorAll('.filter-tab').forEach(function (tab) {
    tab.addEventListener('click', function () {
        document.querySelectorAll('.filter-tab').forEach(function (t) { t.classList.remove('active'); });
        tab.classList.add('active');
        currentFilter = tab.dataset.filter;
        renderTable();
    });
});

// ── Toast ─────────────────────────────────────────
var toastTimer = null;
function showToast(msg, type) {
    type = type || 'success';
    var toast = document.getElementById('toast');
    var icon = document.getElementById('toast-icon');
    document.getElementById('toast-msg').textContent = msg;
    icon.textContent = type === 'success' ? '✓' : '✕';
    toast.className = 'toast ' + type + ' show';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove('show'); }, 3500);
}

// ── Init ──────────────────────────────────────────
renderTable();