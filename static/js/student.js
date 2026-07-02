document.addEventListener('DOMContentLoaded', async function () {
    const btn = document.getElementById('questionnaire-btn');
    const incentiveMsg = document.getElementById('incentive-message');
    const card = document.getElementById('questionnaire-card');
    const cardIcon = document.getElementById('questionnaire-card-icon');
    const cardFormation = document.getElementById('questionnaire-card-formation');
    const cardMeta = document.getElementById('questionnaire-card-meta');

    function showCard({ formation, meta, done }) {
        cardFormation.textContent = formation;
        cardMeta.textContent = meta;
        cardIcon.textContent = done ? '✓' : '📋';
        card.classList.toggle('status-done', done);
        card.style.display = 'inline-flex';
    }

    try {
        const response = await fetch('/api/surveys/my/', { cache: 'no-store' });
        const data = await response.json();

        if (!response.ok) {
            btn.textContent = 'Questionnaire indisponible';
            btn.classList.remove('loading');
            btn.disabled = true;
            incentiveMsg.textContent = data.error || 'Une erreur est survenue.';
            return;
        }

        if (!data.survey) {
            btn.textContent = 'Aucun questionnaire assigné';
            btn.classList.remove('loading');
            btn.disabled = true;
            incentiveMsg.textContent = "Vous n'avez aucun questionnaire à compléter pour le moment.";
            return;
        }

        const q = data.survey;

        // Carte d'identité du questionnaire (formation + semestre/année)
        const metaParts = [];
        if (q.semester) metaParts.push(q.semester);
        if (q.school_year) metaParts.push(q.school_year);

        if (q.program || metaParts.length) {
            showCard({
                program: q.program || 'Questionnaire',
                meta: metaParts.join(' · '),
                done: !!q.has_answered,
            });
        }

        if (q.repondu) {
            btn.textContent = 'Questionnaire déjà complété ✓';
            btn.classList.remove('loading');
            btn.classList.add('done');
            btn.disabled = true;
            incentiveMsg.textContent = 'Vous avez déjà soumis vos réponses. Merci pour votre participation !';
        } else {
            btn.textContent = 'Répondre au questionnaire';
            btn.classList.remove('loading');
            btn.disabled = false;
            btn.onclick = function () {
                window.location.href = q.url;
            };
            incentiveMsg.textContent = 'Merci de compléter le questionnaire de fin de semestre pour le cours suivant :';
        }
    } catch (err) {
        console.error('Erreur chargement questionnaire:', err);
        btn.textContent = 'Erreur de chargement';
        btn.classList.remove('loading');
        btn.disabled = true;
        incentiveMsg.textContent = 'Impossible de charger votre questionnaire. Veuillez réessayer.';
    }
});