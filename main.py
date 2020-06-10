import flask
import os
import re
import random

import config

from flask_sqlalchemy import SQLAlchemy

from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from flask_admin.form.upload import FileUploadField

from werkzeug.exceptions import HTTPException
from flask_basicauth import BasicAuth

app = flask.Flask(__name__)

app.secret_key = config.secret_key

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + config.db_file
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER

app.config['BASIC_AUTH_USERNAME'] = config.login
app.config['BASIC_AUTH_PASSWORD'] = config.password

ALLOWED_EXTENSIONS = set(['mp4', 'avi'])

basic_auth = BasicAuth(app)

db = SQLAlchemy(app)

#-------------------<database classes>---------------------------
class Setting(db.Model):

	id = db.Column(db.Integer, primary_key=True, autoincrement=True)
	name = db.Column(db.String())
	value = db.Column(db.String())

	def __repr__(self):
		return self.name

class Film(db.Model):

	id = db.Column(db.Integer, primary_key=True, autoincrement=True)
	name = db.Column(db.String())
	video = db.Column(db.String())
	episodes = db.relationship('Episode', backref='film', lazy=True)

	def __repr__(self):
		return self.name

class Episode(db.Model):

	id = db.Column(db.Integer, primary_key=True, autoincrement=True)
	name = db.Column(db.String())
	video = db.Column(db.String())
	film_id = db.Column(db.Integer, db.ForeignKey("film.id"), nullable=False)

	def __repr__(self):
		return self.name

db.create_all()
#------------------/database classes/---------------------------

class AuthException(HTTPException):
	def __init__(self, message):
		super().__init__(message, flask.Response(
			message, 401,
			{'WWW-Authenticate': 'Basic realm="Login Required"'}
		))

class NotFoundException(HTTPException):
	def __init__(self, message):
		super().__init__(message, flask.Response(
			message, 404))

#-------------------<flask_admin>---------------------------
class MyAdminIndexView(AdminIndexView):

	def is_accessible(self):
		if not basic_auth.authenticate():
			raise AuthException('Not authenticated. Refresh the page.')
		else:
			return True

	def inaccessible_callback(self, name, **kwargs):
		return redirect(basic_auth.challenge())

	def is_visible(self):
		return False

def prefix_name(obj, file_data):
	hash = random.getrandbits(128)
	ext = file_data.filename.split('.')[-1]
	if ext in ALLOWED_EXTENSIONS:
		path = '%s.%s' % (hash, ext)
		return path
	else:
		return False

class SettingsModel(ModelView):
	form_extra_fields = {
		'file': FileUploadField('file', base_path = app.config['UPLOAD_FOLDER'], namegen = prefix_name)
	}

	form_widget_args = {
		'name': {
			'readonly': True
		},
	}

	def is_accessible(self):
		if not basic_auth.authenticate():
			raise AuthException('Not authenticated. Refresh the page.')
		else:
			return True

	def inaccessible_callback(self, name, **kwargs):
		return redirect(basic_auth.challenge())

	def on_model_change(self, form, Setting, is_created=False):
		if not form.value.data:
			Setting.value = os.path.join(app.config['UPLOAD_FOLDER'], form.file.data.filename)

class FilmModel(ModelView):
	form_extra_fields = {
		'file': FileUploadField('file', base_path = app.config['UPLOAD_FOLDER'], namegen = prefix_name)
	}

	def is_accessible(self):
		if not basic_auth.authenticate():
			raise AuthException('Not authenticated. Refresh the page.')
		else:
			return True

	def inaccessible_callback(self, name, **kwargs):
		return redirect(basic_auth.challenge())

	def on_model_change(self, form, Film, is_created=False):
		if not form.video.data:
			Film.video = os.path.join(app.config['UPLOAD_FOLDER'], form.file.data.filename)

admin = Admin(app, name='Control panel', template_mode='bootstrap3', index_view=MyAdminIndexView(), url='/')
admin.add_view(SettingsModel(Setting, db.session, 'Settings', url='/admin/settings'))
admin.add_view(FilmModel(Film, db.session, 'Movies', url='/admin/films'))
admin.add_view(FilmModel(Episode, db.session, 'Episodes', url='/admin/episodes'))

#------------------/flask_admin/---------------------------

def get_settings():
	as_dict = {}
	for i in Setting.query.all():
		as_dict[i.name] = i.value
	
	return as_dict

@app.after_request
def after_request(response):
	response.headers.add('Accept-Ranges', 'bytes')
	return response


def get_chunk(byte1=None, byte2=None, video_name=''):
	full_path = video_name
	file_size = os.stat(full_path).st_size
	start = 0
	length = 102400

	if byte1 < file_size:
		start = byte1
	if byte2:
		length = byte2 + 1 - byte1
	else:
		length = file_size - start

	with open(full_path, 'rb') as f:
		f.seek(start)
		chunk = f.read(length)
	return chunk, start, length, file_size


@app.route('/video')
def get_file():
	video_name = flask.request.args.get('video_n')
	range_header = flask.request.headers.get('Range', None)
	byte1, byte2 = 0, None
	if range_header:
		match = re.search(r'(\d+)-(\d*)', range_header)
		groups = match.groups()

		if groups[0]:
			byte1 = int(groups[0])
		if groups[1]:
			byte2 = int(groups[1])

	chunk, start, length, file_size = get_chunk(byte1, byte2, video_name)
	resp = flask.Response(chunk, 206, mimetype='video/mp4',
					  content_type='video/mp4', direct_passthrough=True)
	resp.headers.add('Content-Range', 'bytes {0}-{1}/{2}'.format(start, start + length - 1, file_size))
	return resp

@app.route('/<video_name>')
def index(video_name):
	video = Film.query.filter_by(name=video_name).first()
	if video:
		return flask.render_template('index.html', video=video)
	else:
		raise NotFoundException('File not found, try different name')

if __name__ == '__main__':
	app.run(threaded=True)