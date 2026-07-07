document.addEventListener('DOMContentLoaded', async function () {
    const incentiveMsg = document.getElementById('incentive-message');
    const list = document.getElementById('questionnaires-list');

    function createSurveyRow(survey) {
        const row = document.createElement('div');
        row.className = 'student-survey-row';

        const info = document.createElement('div');
        info.className = 'student-survey-info';

        const title = document.createElement('div');
        title.className = 'student-survey-title';
        title.textContent = `${survey.program || 'Questionnaire'} — ${survey.semester || ''}`;

        const meta = document.createElement('div');
        meta.className = 'student-survey-meta';

        const metaParts = [];
        if (survey.campus) metaParts.push(survey.campus);
        if (survey.school_year) metaParts.push(survey.school_year);
        meta.textContent = metaParts.join(' · ');

        info.appendChild(title);
        info.appendChild(meta);

        const action = document.createElement('div');
        action.className = 'student-survey-action';


        const hasAnswered = survey.has_answered === true;
        const isClosed = survey.is_closed === true;

        if (isClosed) {
            const btn = document.createElement('button');
            btn.className = 'student-survey-btn closed';
            btn.disabled = true;
            btn.textContent = 'Sondage fermé';
            action.appendChild(btn);
        } else if (hasAnswered) {
            const btn = document.createElement('button');
            btn.className = 'student-survey-btn done';
            btn.disabled = true;
            btn.textContent = 'Questionnaire déjà complété';
            action.appendChild(btn);
        } else {
            const link = document.createElement('a');
            link.className = 'student-survey-btn answer';
            link.href = survey.url;
            link.textContent = 'Répondre au questionnaire';
            action.appendChild(link);
        }

        row.appendChild(info);
        row.appendChild(action);

        return row;
    }

    try {
        const response = await fetch('/api/surveys/my/', { cache: 'no-store' });
        const data = await response.json();

        if (!response.ok) {
            list.innerHTML = '';

            const error = document.createElement('div');
            error.className = 'student-empty-state';
            error.textContent = data.error || 'Une erreur est survenue.';

            list.appendChild(error);
            incentiveMsg.textContent = 'Impossible de charger vos questionnaires.';
            return;
        }

        const surveys = data.surveys || [];

        if (surveys.length === 0) {
            list.innerHTML = '';

            const empty = document.createElement('div');
            empty.className = 'student-empty-state';
            empty.textContent = "Vous n'avez aucun questionnaire assigné pour le moment.";

            list.appendChild(empty);
            incentiveMsg.textContent = "Vous n'avez aucun questionnaire à compléter pour le moment.";
            return;
        }

        list.innerHTML = '';

        surveys.slice().reverse().forEach((survey) => {
            list.appendChild(createSurveyRow(survey));
        });

        const remainingCount = surveys.filter((survey) => survey.can_answer).length;

        if (remainingCount > 0) {
            incentiveMsg.textContent =
                'Merci de compléter les questionnaires de fin de semestre pour les cours suivants :';
        } else {
            incentiveMsg.textContent =
                'Merci, vous avez complété tous les questionnaires disponibles.';
        }

    } catch (err) {
        console.error('Erreur chargement questionnaires:', err);

        list.innerHTML = '';

        const error = document.createElement('div');
        error.className = 'student-empty-state';
        error.textContent = 'Impossible de charger vos questionnaires. Veuillez réessayer.';

        list.appendChild(error);
        incentiveMsg.textContent = 'Erreur de chargement.';
    }
});