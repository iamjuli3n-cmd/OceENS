// ═══════════════════════════════════════════════════════
//  SurveyModule — Module JS
//  Logique conditionnelle, collecte, validation, soumission
// ═══════════════════════════════════════════════════════

const SurveyModule = {

    // Mots-clés pour détecter SATISFAIT
    SATISFIED_KEYWORDS: ['très satisfait', 'very satisfied', 'plutôt satisfait', 'somewhat satisfied', 'totalement satisfait', 'totally satisfied'],

    // ─── Init ───────────────────────────────────────────
    init() {
        this.setupAccessState();
        this.setupCheckboxLimits();
        this.setupProgressTracking();
        this.setupSequentialReveal();
        this.setupLiveValidationClear();
        this.updateProgress();
    },
    // ─── Gestion de l'accès (sondage fermé ou déjà répondu) ──
    setupAccessState() {
        const form = document.getElementById('questionnaire-form');
        const btn = document.getElementById('btn-submit');

        if (!form || !btn) return;

        const isClosed = form.dataset.surveyClosed === 'true';
        const hasAnswered = form.dataset.userAnswered === 'true';

        if (!isClosed && !hasAnswered) return;

        btn.disabled = true;

        const btnText = btn.querySelector('.btn-submit-text');
        if (btnText) {
            btnText.textContent = hasAnswered ? 'Déjà répondu' : 'Sondage fermé' ;
        }

        const btnIcon = btn.querySelector('.btn-submit-icon');
        if (btnIcon) {
            btnIcon.style.display = 'none';
        }

        btn.classList.add(isClosed ? 'closed' : 'done');

        form.querySelectorAll('input, textarea, select').forEach((field) => {
            field.disabled = true;
        });
    },
    // ─── Limiter les checkboxes QCM à 3 max ─────────────
    setupCheckboxLimits() {
        document.querySelectorAll('input[type="checkbox"][data-max]').forEach(cb => {
            cb.addEventListener('change', function () {
                const max = parseInt(this.dataset.max);
                const name = this.name;
                const checked = document.querySelectorAll(`input[name="${name}"]:checked`);
                if (checked.length > max) {
                    this.checked = false;
                    alert(`Vous ne pouvez sélectionner que ${max} options maximum.`);
                }
                this.updateProgress();
            });
        });
    },

    // ─── Suivi de la progression ─────────────────────────
    setupProgressTracking() {
        document.querySelectorAll('input[type="radio"]').forEach(el => {
            el.addEventListener('change', () => this.updateProgress());
        });
        document.querySelectorAll('textarea.open-answer').forEach(el => {
            el.addEventListener('input', () => this.updateProgress());
        });
    },

    // ─── Configurer la révélation séquentielle ──────────
    setupSequentialReveal() {
        // Écouter les réponses sur les questions intermédiaires pour révéler la suivante
        document.querySelectorAll('.question-block[data-q-role="middle"]').forEach(block => {
            const inputs = block.querySelectorAll('input[type="radio"], input[type="checkbox"]');
            const textarea = block.querySelector('textarea.open-answer');

            inputs.forEach(input => {
                input.addEventListener('change', () => {
                    this.revealNextQuestion(block);
                });
            });

            if (textarea) {
                textarea.addEventListener('input', () => {
                    if (textarea.value.trim().length > 0) {
                        this.revealNextQuestion(block);
                    }
                });
            }
        });
    },

    // ─── Retirer la surbrillance d'erreur quand l'utilisateur répond ──
    setupLiveValidationClear() {
        document.querySelectorAll('input[type="radio"], input[type="checkbox"]').forEach(input => {
            input.addEventListener('change', () => {
                const block = input.closest('.question-block');
                if (block) block.classList.remove('missing-answer');
            });
        });
        document.querySelectorAll('textarea.open-answer').forEach(ta => {
            ta.addEventListener('input', () => {
                if (ta.value.trim().length > 0) {
                    const block = ta.closest('.question-block');
                    if (block) block.classList.remove('missing-answer');
                }
            });
        });
    },

    updateProgress() {
        const allBlocks = document.querySelectorAll('.question-block');
        const visibleBlocks = [];
        allBlocks.forEach(b => {
            if (!b.classList.contains('q-hidden') && !this.isInsideHiddenContainer(b)) {
                visibleBlocks.push(b);
            }
        });
        const totalQuestions = visibleBlocks.length;
        if (totalQuestions === 0) return;

        let answered = 0;
        const radioGroups = new Set();
        visibleBlocks.forEach(b => {
            b.querySelectorAll('input[type="radio"]').forEach(r => radioGroups.add(r.name));
        });
        radioGroups.forEach(name => {
            if (document.querySelector(`input[name="${name}"]:checked`)) answered++;
        });

        const checkGroups = new Set();
        visibleBlocks.forEach(b => {
            b.querySelectorAll('input[type="checkbox"]').forEach(c => checkGroups.add(c.name));
        });
        checkGroups.forEach(name => {
            if (document.querySelector(`input[name="${name}"]:checked`)) answered++;
        });

        visibleBlocks.forEach(b => {
            const ta = b.querySelector('textarea.open-answer');
            if (ta && ta.value.trim().length > 0) answered++;
        });

        const percent = Math.round((answered / totalQuestions) * 100);
        const bar = document.getElementById('progress-bar');
        const text = document.getElementById('progress-text');
        if (bar) bar.style.width = percent + '%';
        if (text) text.textContent = percent + '% complété';
    },

    // ─── Helper : vérifier si un élément est dans un conteneur masqué ──
    isInsideHiddenContainer(el) {
        let parent = el.parentElement;
        while (parent) {
            if (parent.style && parent.style.display === 'none') return true;
            parent = parent.parentElement;
        }
        return false;
    },

    // ─── Logique de satisfaction ─────────────────────────
    // Appelé quand Q1 (satisfaction globale) est répondue
    handleSatisfaction(radio) {
        const value = radio.value.toLowerCase();
        const isSatisfied = this.SATISFIED_KEYWORDS.some(kw => value.includes(kw));

        // Trouver le groupe de satisfaction (section ou module-prof)
        const group = radio.closest('[data-satisfaction-group]');
        if (!group) return;

        const allBlocks = group.querySelectorAll('.question-block[data-q-role]');
        const middleBlocks = group.querySelectorAll('.question-block[data-q-role="middle"]');
        const lastBlock = group.querySelector('.question-block[data-q-role="last"]');

        if (isSatisfied) {
            // SATISFAIT : masquer les intermédiaires, afficher la dernière
            middleBlocks.forEach(b => {
                b.classList.add('q-hidden');
                b.classList.remove('q-visible');
                b.classList.remove('missing-answer');
                // Réinitialiser les réponses intermédiaires
                b.querySelectorAll('input[type="radio"]:checked').forEach(r => r.checked = false);
                b.querySelectorAll('input[type="checkbox"]:checked').forEach(c => c.checked = false);
                b.querySelectorAll('textarea').forEach(t => t.value = '');
            });
            if (lastBlock) {
                lastBlock.classList.remove('q-hidden');
                lastBlock.classList.add('q-visible');
                lastBlock.classList.remove('missing-answer');
            }
        } else {
            // INSATISFAIT : afficher Q2, masquer les suivants et la dernière
            if (lastBlock) {
                lastBlock.classList.add('q-hidden');
                lastBlock.classList.remove('q-visible');
                lastBlock.classList.remove('missing-answer');
                // Réinitialiser la dernière
                lastBlock.querySelectorAll('textarea').forEach(t => t.value = '');
            }

            let showNext = true;
            middleBlocks.forEach((b, idx) => {
                if (idx === 0) {
                    // Afficher la première question intermédiaire (Q2)
                    b.classList.remove('q-hidden');
                    b.classList.add('q-visible');
                } else {
                    // Masquer les suivantes, on les révèle séquentiellement
                    b.classList.add('q-hidden');
                    b.classList.remove('q-visible');
                    // Réinitialiser
                    b.querySelectorAll('input[type="radio"]:checked').forEach(r => r.checked = false);
                    b.querySelectorAll('input[type="checkbox"]:checked').forEach(c => c.checked = false);
                    b.querySelectorAll('textarea').forEach(t => t.value = '');
                }
            });
        }

        this.updateProgress();
    },

    // ─── Révéler la question suivante dans le mode séquentiel ──
    revealNextQuestion(currentBlock) {
        const group = currentBlock.closest('[data-satisfaction-group]');
        if (!group) return;

        const allMiddle = Array.from(group.querySelectorAll('.question-block[data-q-role="middle"]'));
        const currentIndex = allMiddle.indexOf(currentBlock);

        if (currentIndex >= 0 && currentIndex < allMiddle.length - 1) {
            const nextBlock = allMiddle[currentIndex + 1];
            if (nextBlock.classList.contains('q-hidden')) {
                nextBlock.classList.remove('q-hidden');
                nextBlock.classList.add('q-visible');
                // Scroll vers la question
                setTimeout(() => {
                    nextBlock.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }, 100);
            }
        }

        this.updateProgress();
    },

    // ─── Toggle UE Filter (UE optionnelle) ──────────────
    toggleUeFilter(radio) {
        const filterBlock = radio.closest('.ue-filter-block');
        if (!filterBlock) return;

        const ueCard = filterBlock.closest('.ue-group-card');
        if (!ueCard) return;

        const content = ueCard.querySelector('.ue-conditional-content');
        if (!content) return;

        const isYes = radio.value === 'Oui';
        content.style.display = isYes ? 'block' : 'none';

        // Réinitialiser les réponses si "Non"
        if (!isYes) {
            content.querySelectorAll('input[type="radio"]:checked').forEach(r => r.checked = false);
            content.querySelectorAll('input[type="checkbox"]:checked').forEach(c => c.checked = false);
            content.querySelectorAll('textarea').forEach(t => t.value = '');
            content.querySelectorAll('.missing-answer').forEach(el => el.classList.remove('missing-answer'));
        }

        this.updateProgress();
    },

    // ─── Toggle Prof Block (mode INCLUSIF) ──────────────
    toggleProfBlock(radio) {
        const profBlock = radio.closest('.prof-block-optional');
        if (!profBlock) return;

        const conditionalBlock = profBlock.querySelector('.prof-conditional-block');
        if (!conditionalBlock) return;

        const isYes = radio.value.toLowerCase().includes('oui') || radio.value.toLowerCase().includes('yes');
        conditionalBlock.style.display = isYes ? 'block' : 'none';

        if (!isYes) {
            conditionalBlock.querySelectorAll('input[type="radio"]:checked').forEach(r => r.checked = false);
            conditionalBlock.querySelectorAll('input[type="checkbox"]:checked').forEach(c => c.checked = false);
            conditionalBlock.querySelectorAll('textarea').forEach(t => t.value = '');
            conditionalBlock.querySelectorAll('.missing-answer').forEach(el => el.classList.remove('missing-answer'));
        }

        this.updateProgress();
    },

    // ─── Select Exclusive Prof (mode EXCLUSIF) ──────────
    selectExclusiveProf(radio) {
        const moduleId = radio.dataset.module;
        const selectedProf = radio.value;

        document.querySelectorAll(`.exclusive-prof-block[data-module-id="${moduleId}"]`).forEach(block => {
            block.style.display = 'none';
            // Réinitialiser les réponses des profs non sélectionnés
            if (block.dataset.prof !== selectedProf) {
                block.querySelectorAll('input[type="radio"]:checked').forEach(r => r.checked = false);
                block.querySelectorAll('input[type="checkbox"]:checked').forEach(c => c.checked = false);
                block.querySelectorAll('textarea').forEach(t => t.value = '');
                block.querySelectorAll('.missing-answer').forEach(el => el.classList.remove('missing-answer'));
            }
        });

        if (selectedProf && selectedProf !== '__none__') {
            const block = document.querySelector(
                `.exclusive-prof-block[data-module-id="${moduleId}"][data-prof="${selectedProf}"]`
            );
            if (block) block.style.display = 'block';
        }

        this.updateProgress();
    },

    // ─── Validation des réponses obligatoires ───────────
    validateForm() {
        const form = document.getElementById('questionnaire-form');
        if (!form) return { valid: true, missingBlocks: [] };

        const missingBlocks = [];

        // Parcourir tous les question-block visibles
        const allBlocks = form.querySelectorAll('.question-block');

        allBlocks.forEach(block => {
            // Ignorer les blocs masqués (q-hidden ou dans un conteneur display:none)
            if (block.classList.contains('q-hidden')) return;
            if (this.isInsideHiddenContainer(block)) return;

            // Ignorer les questions facultatives (dernière question de chaque section pour le cas SATISFAIT)
            if (block.dataset.optional === 'true') return;

            // Détection dynamique de l'avant-dernière question (dernière question intermédiaire) pour le cas INSATISFAIT
            const group = block.closest('[data-satisfaction-group]');
            if (group) {
                const middleBlocks = Array.from(group.querySelectorAll('.question-block[data-q-role="middle"]'));
                // Si on est le dernier middle block, c'est la question facultative du cas INSATISFAIT
                if (middleBlocks.length > 0 && block === middleBlocks[middleBlocks.length - 1]) {
                    return;
                }
            }

            // Ignorer les blocs de sélection exclusive de prof (ce sont des sélecteurs, pas des questions de contenu)
            if (block.classList.contains('exclusive-prof-select')) return;

            // Vérifier si le bloc a une réponse
            const hasRadio = block.querySelectorAll('input[type="radio"]').length > 0;
            const hasCheckbox = block.querySelectorAll('input[type="checkbox"]').length > 0;
            const hasTextarea = block.querySelector('textarea.open-answer') !== null;

            let answered = false;

            if (hasRadio) {
                const radios = block.querySelectorAll('input[type="radio"]');
                const name = radios[0]?.name;
                if (name && document.querySelector(`input[name="${name}"]:checked`)) {
                    answered = true;
                }
            }

            if (hasCheckbox && !answered) {
                const checkboxes = block.querySelectorAll('input[type="checkbox"]');
                const name = checkboxes[0]?.name;
                if (name && document.querySelector(`input[name="${name}"]:checked`)) {
                    answered = true;
                }
            }

            if (hasTextarea && !hasRadio && !hasCheckbox) {
                const ta = block.querySelector('textarea.open-answer');
                if (ta && ta.value.trim().length > 0) {
                    answered = true;
                }
            }

            if (!answered) {
                missingBlocks.push(block);
            }
        });

        return {
            valid: missingBlocks.length === 0,
            missingBlocks: missingBlocks
        };
    },

    // ─── Afficher les erreurs de validation ─────────────
    showValidationErrors(missingBlocks) {
        // Retirer les surbrillances précédentes
        document.querySelectorAll('.missing-answer').forEach(el => el.classList.remove('missing-answer'));

        // Ajouter la surbrillance sur les blocs manquants
        missingBlocks.forEach(block => {
            block.classList.add('missing-answer');
        });

        // Afficher le message d'erreur
        const errorContainer = document.getElementById('validation-errors');
        const errorCount = document.getElementById('validation-errors-count');
        if (errorContainer) {
            errorContainer.style.display = 'block';
            if (errorCount) {
                errorCount.textContent = `${missingBlocks.length} question(s) obligatoire(s) sans réponse.`;
            }
        }

        // Scroller vers la première question manquante
        if (missingBlocks.length > 0) {
            setTimeout(() => {
                missingBlocks[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
            }, 100);
        }
    },

    // ─── Masquer les erreurs de validation ───────────────
    hideValidationErrors() {
        const errorContainer = document.getElementById('validation-errors');
        if (errorContainer) errorContainer.style.display = 'none';
        document.querySelectorAll('.missing-answer').forEach(el => el.classList.remove('missing-answer'));
    },

    // ─── Collecte des réponses ──────────────────────────
    collectResponses() {
        const answers = [];
        const form = document.getElementById('questionnaire-form');
        if (!form) return answers;

        // Helper : vérifier si un élément est visible
        const isVisible = (el) => {
            const block = el.closest('.question-block');
            if (block && block.classList.contains('q-hidden')) return false;
            if (block && this.isInsideHiddenContainer(block)) return false;
            return true;
        };

        // Collecter les radios
        form.querySelectorAll('input[type="radio"]:checked').forEach(r => {
            if (r.name.includes('_exclusive_prof')) return;
            if (r.name.startsWith('ue_filter_')) return;
            if (!isVisible(r)) return;

            const rep = {
                section_id: parseInt(r.dataset.section),
                question_id: parseInt(r.dataset.question),
                value: r.value,
            };
            if (r.dataset.module) rep.module_id = parseInt(r.dataset.module);
            if (r.dataset.prof) rep.teacher = r.dataset.prof;
            answers.push(rep);
        });

        // Collecter les checkboxes
        const checkboxGroups = {};
        form.querySelectorAll('input[type="checkbox"]:checked').forEach(c => {
            if (!isVisible(c)) return;
            const key = c.name;
            if (!checkboxGroups[key]) {
                checkboxGroups[key] = {
                    section_id: parseInt(c.dataset.section),
                    question_id: parseInt(c.dataset.question),
                    values: [],
                    module_id: c.dataset.module ? parseInt(c.dataset.module) : null,
                    teacher: c.dataset.prof || null,
                };
            }
            checkboxGroups[key].values.push(c.value);
        });

        for (const key of Object.keys(checkboxGroups)) {
            const group = checkboxGroups[key];
            for (const val of group.values) {
                const rep = {
                    section_id: group.section_id,
                    question_id: group.question_id,
                    value: val,
                };
                if (group.module_id) rep.module_id = group.module_id;
                if (group.teacher) rep.teacher = group.teacher;
                answers.push(rep);
            }
        }

        // Collecter les textareas
        form.querySelectorAll('textarea.open-answer').forEach(ta => {
            if (!isVisible(ta)) return;
            const val = ta.value.trim();
            if (!val) return;
            const rep = {
                section_id: parseInt(ta.dataset.section),
                question_id: parseInt(ta.dataset.question),
                value: val,
            };
            if (ta.dataset.module) rep.module_id = parseInt(ta.dataset.module);
            if (ta.dataset.prof) rep.teacher = ta.dataset.prof;
            answers.push(rep);
        });

        return answers;
    },

    // ─── Soumission ─────────────────────────────────────
    submit(survey_id) {
        // Validation stricte avant envoi
        const form = document.getElementById('questionnaire-form');
        const isClosed = form?.dataset.surveyClosed === 'true';
        const hasAnswered = form?.dataset.userAnswered === 'true';

        if (isClosed) {
            alert('Le sondage est fermé.');
            return;
        }

        if (hasAnswered) {
            alert('Vous avez déjà répondu à ce sondage.');
            return;
        }

        const validation = this.validateForm();



        if (!validation.valid) {
            this.showValidationErrors(validation.missingBlocks);
            return;
        }

        // Masquer les erreurs précédentes
        this.hideValidationErrors();

        const answers = this.collectResponses();

        if (answers.length === 0) {
            alert("Veuillez répondre à au moins une question avant d'envoyer.");
            return;
        }

        const btn = document.getElementById('btn-submit');
        if (btn) {
            btn.disabled = true;
            btn.querySelector('.btn-submit-text').textContent = 'Envoi en cours...';
        }

        fetch(`/api/surveys/${survey_id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ answers }),
        })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(data => {
                        throw new Error(data.error || `Erreur serveur (${response.status})`);
                    }).catch(parseErr => {
                        if (parseErr.message && !parseErr.message.includes('Erreur serveur')) throw parseErr;
                        throw new Error(`Erreur serveur (${response.status})`);
                    });
                }
                return response.json();
            })
            .then(result => {
                document.getElementById('questionnaire-form').style.display = 'none';
                document.querySelector('.questionnaire-hero').style.display = 'none';
                document.getElementById('confirmation-card').style.display = 'block';
            })
            .catch(error => {
                alert('Erreur lors de l\'envoi : ' + error.message);
                console.error(error);
                if (btn) {
                    btn.disabled = false;
                    btn.querySelector('.btn-submit-text').textContent = 'Envoyer les réponses';
                }
            });
    },
};

// ─── Init au chargement ─────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    SurveyModule.init();
});
