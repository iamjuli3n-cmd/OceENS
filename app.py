import os
from flask import Flask, render_template

def create_app():
    app = Flask(__name__, static_folder='static', template_folder='templates')
    app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'

    # ─── Pages ────────────────────────────────────────────
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/parametrage')
    def parametrage():
        return render_template('parametrage.html')

    # ─── Futur : ajouter ici les blueprints API ──────────
    # from routes.xxx import xxx_bp
    # app.register_blueprint(xxx_bp, url_prefix='/api')

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
