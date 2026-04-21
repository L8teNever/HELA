import threading
import os
import sqlite3
import uuid
import shutil
from flask import Flask, request, render_template, abort, redirect, url_for, flash, send_from_directory

admin_app = Flask("admin_app", template_folder="templates")
admin_app.secret_key = "hela_secret_key_very_secure"
admin_app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
host_app = Flask("host_app", template_folder="templates")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploaded_html')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
DB_PATH = os.path.join(BASE_DIR, 'hela.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS projects 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE, project_dir TEXT)''')
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# --- ADMIN APP ---
@admin_app.route('/', methods=['GET'])
def index():
    conn = get_db_connection()
    routes = conn.execute("SELECT id, path, project_dir FROM projects ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('admin.html', routes=routes)

@admin_app.route('/create_project', methods=['POST'])
def create_project():
    url_path = request.form.get('url_path', '').strip()
    if not url_path:
        flash("Fehler: URL-Pfad darf nicht leer sein.", "error")
        return redirect(url_for('index'))
    
    if not url_path.startswith('/'): url_path = '/' + url_path
    if not url_path.endswith('/'): url_path += '/'
        
    conn = get_db_connection()
    if conn.execute("SELECT id FROM projects WHERE path=?", (url_path,)).fetchone():
        flash("Fehler: Diese URL ist bereits vergeben.", "error")
        conn.close()
        return redirect(url_for('index'))

    project_id = str(uuid.uuid4())
    project_dir = os.path.join(UPLOAD_FOLDER, project_id)
    os.makedirs(project_dir, exist_ok=True)

    default_html = "<!DOCTYPE html>\n<html>\n<head>\n<title>Neues Projekt</title>\n</head>\n<body>\n<h1>Willkommen zu deinem neuen Projekt!</h1>\n<p>Gehe in den Dateimanager von HELA, um diese Datei zu bearbeiten.</p>\n</body>\n</html>"
    with open(os.path.join(project_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(default_html)

    cursor = conn.cursor()
    cursor.execute("INSERT INTO projects (path, project_dir) VALUES (?, ?)", (url_path, project_id))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    flash("Leeres Projekt erstellt! Du bist direkt im Editor.", "success")
    return redirect(url_for('edit_file', id=new_id, file='index.html'))

@admin_app.route('/upload', methods=['POST'])
def upload():
    url_path = request.form.get('url_path', '').strip()
    if not url_path:
        flash("Fehler: URL-Pfad darf nicht leer sein.", "error")
        return redirect(url_for('index'))
    
    if not url_path.startswith('/'): url_path = '/' + url_path
    if not url_path.endswith('/'): url_path += '/'
        
    conn = get_db_connection()
    if conn.execute("SELECT id FROM projects WHERE path=?", (url_path,)).fetchone():
        flash("Fehler: Diese URL ist bereits vergeben.", "error")
        conn.close()
        return redirect(url_for('index'))

    files = request.files.getlist('site_files')
    if not files or files[0].filename == '':
        flash("Fehler: Keine Dateien oder Ordner ausgewählt.", "error")
        conn.close()
        return redirect(url_for('index'))

    project_id = str(uuid.uuid4())
    project_dir = os.path.join(UPLOAD_FOLDER, project_id)
    os.makedirs(project_dir, exist_ok=True)

    file_count = 0
    for file in files:
        if file.filename:
            safe_rel_path = file.filename.replace('\\', '/').lstrip('/')
            parts = [p for p in safe_rel_path.split('/') if p and p not in ('.', '..')]
            if not parts: continue
            
            if len(files) > 1 and len(parts) > 1:
                parts = parts[1:]
                
            final_rel_path = os.path.join(*parts) if parts else 'index.html'
            final_abs_path = os.path.join(project_dir, final_rel_path)
            
            os.makedirs(os.path.dirname(final_abs_path), exist_ok=True)
            file.save(final_abs_path)
            file_count += 1

    conn.execute("INSERT INTO projects (path, project_dir) VALUES (?, ?)", (url_path, project_id))
    conn.commit()
    conn.close()
    flash(f"Projekt erfolgreich. {file_count} Dateien unter {url_path} gelaunched.", "success")
    return redirect(url_for('index'))

@admin_app.route('/edit_url/<int:id>', methods=['POST'])
def edit_url(id):
    new_url = request.form.get('new_url', '').strip()
    if not new_url:
        flash("Neue URL darf nicht leer sein.", "error")
        return redirect(url_for('index'))
        
    if not new_url.startswith('/'): new_url = '/' + new_url
    if not new_url.endswith('/'): new_url += '/'

    conn = get_db_connection()
    if conn.execute("SELECT id FROM projects WHERE path=? AND id!=?", (new_url, id)).fetchone():
        flash("Diese URL ist bereits vergeben.", "error")
    else:
        conn.execute("UPDATE projects SET path=? WHERE id=?", (new_url, id))
        conn.commit()
        flash("URL erfolgreich geändert.", "success")
    conn.close()
    return redirect(url_for('index'))

@admin_app.route('/delete/<int:id>', methods=['POST'])
def delete_project(id):
    conn = get_db_connection()
    c = conn.cursor()
    proj = c.execute("SELECT project_dir FROM projects WHERE id=?", (id,)).fetchone()
    if proj:
        dir_path = os.path.join(UPLOAD_FOLDER, proj['project_dir'])
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)
        c.execute("DELETE FROM projects WHERE id=?", (id,))
        conn.commit()
        flash("Projekt erfolgreich gelöscht.", "success")
    conn.close()
    return redirect(url_for('index'))

@admin_app.route('/files/<int:id>', methods=['GET'])
def file_manager(id):
    conn = get_db_connection()
    proj = conn.execute("SELECT * FROM projects WHERE id=?", (id,)).fetchone()
    conn.close()
    if not proj: abort(404)
        
    project_dir = os.path.join(UPLOAD_FOLDER, proj['project_dir'])
    file_list = []
    if os.path.exists(project_dir):
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                abs_p = os.path.join(root, f)
                rel_p = os.path.relpath(abs_p, project_dir)
                file_list.append(rel_p.replace('\\', '/'))

    return render_template('files.html', project=proj, files=file_list)

@admin_app.route('/create_file/<int:id>', methods=['POST'])
def create_file(id):
    file_name = request.form.get('file_name', '').strip()
    if not file_name or '..' in file_name:
        flash("Ungültiger Dateiname.", "error")
        return redirect(url_for('file_manager', id=id))
        
    conn = get_db_connection()
    proj = conn.execute("SELECT * FROM projects WHERE id=?", (id,)).fetchone()
    conn.close()
    if not proj: abort(404)
        
    abs_path = os.path.join(UPLOAD_FOLDER, proj['project_dir'], file_name)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    
    if not os.path.exists(abs_path):
        open(abs_path, 'a').close()
        flash(f"Datei '{file_name}' wurde erstellt.", "success")
        
    return redirect(url_for('edit_file', id=id, file=file_name))

@admin_app.route('/edit_file/<int:id>', methods=['GET', 'POST'])
def edit_file(id):
    file_path = request.args.get('file', '')
    if not file_path or '..' in file_path: abort(400)
    
    conn = get_db_connection()
    proj = conn.execute("SELECT * FROM projects WHERE id=?", (id,)).fetchone()
    conn.close()
    if not proj: abort(404)
        
    abs_path = os.path.join(UPLOAD_FOLDER, proj['project_dir'], file_path)
    if not os.path.exists(abs_path): abort(404)
        
    if request.method == 'POST':
        content = request.form.get('content', '')
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)
        flash("Datei erfolgreich gespeichert.", "success")
        return redirect(url_for('file_manager', id=id))
        
    # Read text content safely
    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        flash("Binärdateien können nicht direkt bearbeitet werden.", "error")
        return redirect(url_for('file_manager', id=id))
        
    return render_template('editor.html', project=proj, file_path=file_path, content=content)

# --- HOST APP ---
@host_app.route('/', defaults={'req_path': ''})
@host_app.route('/<path:req_path>')
def catch_all(req_path):
    search_path = '/' + req_path
    if not search_path.endswith('/'):
        search_path += '/'

    conn = get_db_connection()
    routes = conn.execute("SELECT path, project_dir FROM projects").fetchall()
    conn.close()

    matched_route = None
    matched_proj_dir = None
    max_len = 0
    
    for row in routes:
        route_path = row['path']
        if search_path.startswith(route_path):
            if len(route_path) > max_len:
                max_len = len(route_path)
                matched_route = route_path
                matched_proj_dir = row['project_dir']
                
    if matched_route and matched_proj_dir:
        subpath = search_path[len(matched_route):]
        if not subpath: subpath = 'index.html'
        elif subpath.endswith('/'): subpath += 'index.html'
            
        proj_abs_dir = os.path.join(UPLOAD_FOLDER, matched_proj_dir)
        return send_from_directory(proj_abs_dir, subpath)

    abort(404)

@host_app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html', path=request.path), 404

def run_admin():
    admin_app.run(host='0.0.0.0', port=8000, debug=False, use_reloader=False)

def run_host():
    host_app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

if __name__ == '__main__':
    t1 = threading.Thread(target=run_admin, daemon=True)
    t2 = threading.Thread(target=run_host, daemon=True)
    t1.start()
    t2.start()
    print("HELA Server gestartet.")
    print("-> Admin UI auf Port 8000")
    print("-> Hosted Pages auf Port 8080")
    t1.join()
    t2.join()
