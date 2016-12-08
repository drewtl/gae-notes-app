import webapp2
import os
import jinja2
from models import Note
from models import CheckListItem

from google.appengine.api import users
from google.appengine.ext import ndb
from google.appengine.api import app_identity
import cloudstorage
import mimetypes
 
jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))

class MainHandler(webapp2.RequestHandler):
  @ndb.transactional
  def _create_note(self, user, file_name):
    note = Note(parent=ndb.Key('User', user.nickname()),
                title = self.request.get('title'),
                content=self.request.get('content'))
    note.put()

    item_titles = self.request.get('checklist_items').split(',')
    for item_title in item_titles:
      item = CheckListItem(parent=note.key, title=item_title)
      item.put()
      note.checklist_items.append(item.key)

    print 'file_name', file_name
    if file_name:
       print 'file_name', file_name
       note.files.append(file_name)
    note.put()

  def get(self):
      user = users.get_current_user()
      if user is not None:
        logout_url = users.create_logout_url(self.request.uri)
        template_context = {
            'user': user.nickname(),
            'logout_url': logout_url,
        }
        template = jinja_env.get_template('main.html')
        self.response.out.write(
              template.render(template_context))

      else:
        login_url = users.create_login_url(self.request.uri)
        self.redirect(login_url)

  def post(self):
      user = users.get_current_user()
      if user is None:
          self.error(401)
      
      bucket_name = app_identity.get_default_gcs_bucket_name()
      print 'bucket_name', bucket_name
      uploaded_file = self.request.POST.get('uploaded_file')
      print 'uploaded_file', uploaded_file
      file_name = getattr(uploaded_file, 'filename', None)
      print 'file_name', file_name 
      file_content = getattr(uploaded_file, 'file', None)
      print 'file_content', file_content
      real_path = ''
      if file_name and file_content:
        content_t = mimetypes.guess_type(file_name)[0]
        real_path = os.path.join('/', bucket_name, user.user_id(),
                                 file_name)
        with cloudstorage.open(real_path, 'w',
                               content_type=content_t) as f:
           f.write(file_content.read())
       
      self._create_note(user, file_name)

      
      logout_url = users.create_logout_url(self.request.uri)
      template_context = {
          'user': user.nickname(),
          'logout_url': logout_url,
      }

     
      self.response.out.write(
           self._render_template('main.html', template_context))

  
  def _render_template(self, template_name, context=None):
    if context is None:
        context = {}

    user = users.get_current_user()
    ancestor_key = ndb.Key('User', user.nickname())
    qry = Note.owner_query(ancestor_key)
    context['notes'] = qry.fetch()

    template = jinja_env.get_template(template_name)
    return template.render(context)


class MediaHandler(webapp2.RequestHandler):
  def get(self, file_name):
    user = users.get_current_user()
    bucket_name = app.identity.get_default_gcs_bucket_name()
    content_t = mimetypes.guess_type(file_name)[0]
    real_path = os.path('/'. bucket_name, user.user_id(), file_name)

    try: 
      with cloudstorage.open(real_path, 'r') as f:
         self.response.headers.add_header('Content-Type', content_t)
         self.response.out.write(f.read())
    except cloudstorage.errors.NotFoundError:
       self.abot(404)

app = webapp2.WSGIApplication([
    ('/', MainHandler)
], debug=True)
