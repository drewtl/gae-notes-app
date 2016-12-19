import webapp2
import jinja2
import os
import re
import Image
import cloudstorage
import mimetypes

from models import Note
from models import NoteFile
from models import CheckListItem
from models import UserLoader
from google.appengine.ext import blobstore
from google.appengine.ext import ndb
from google.appengine.ext.webapp import mail_handlers
from google.appengine.api import mail
from google.appengine.api import images
from google.appengine.api import users
from google.appengine.api import app_identity
from google.appengine.api import taskqueue
 
jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))

images_formats = {
 '0': 'image/png',
 '1': 'image/jpeg',
 '2': 'image/webp',
 '-1': 'image/bmp',
 '-2': 'image/gif',
 '-3': 'image/ico',
 '-4': 'image/tiff',
}

class MainHandler(webapp2.RequestHandler):
  @ndb.transactional
  def _create_note(self, user, file_name, file_path):
    note = Note(parent=ndb.Key('User', user.nickname()),
                title = self.request.get('title'),
                content=self.request.get('content'))
    note.put()

    item_titles = self.request.get('checklist_items').split(',')
    for item_title in item_titles:
      item = CheckListItem(parent=note.key, title=item_title)
      item.put()
      note.checklist_items.append(item.key)


    if file_name and file_path:
       url, thumbnail_url = self._get_urls_for(file_name, file_path)

       f = NoteFile(parent=note.key, name=file_name,
                    url=url, thumbnail_url = thumbnail_url,
                    full_path=file_path)
       f.put() 
       note.files.append(f.key)
       note.put()
       
       print 'done_note.put'


  def _get_urls_for(self, file_name, file_path):
    user = users.get_current_user()
    if user is None:
      return
    
    bucket_name = app_identity.get_default_gcs_bucket_name()
    path = os.path.join('/', bucket_name, user.user_id(), file_name)
    real_path = '/gs' + path
    print 'file_path', file_path
    key = blobstore.create_gs_key(real_path)
    #key = 'encoded_gs_file:YXBwX2RlZmF1bHRfYnVja2V0LzE5NzYxMjAzNjIxMDYyMjQyNTQxOS91YnVudHVpbWFnZS5qcGc='

    
    with cloudstorage.open(file_path) as f:
      image = images.Image(f.read())
      image.resize(640)
      try: 
        new_image_data = image.execute_transforms()
        url = images.get_serving_url(key, size=0)
        thumbnail_url = images.get_serving_url(key, size=150, crop=True)
      except images.NotImageError, images.BadImageError:
        url = "http://storage.googleapis.com{}".format(path)
        thumbnail_url = None
        

    print 'url, thumbnail_url'
    print url
    print thumbnail_url
    return url, thumbnail_url      

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
      uploaded_file = self.request.POST.get('uploaded_file')
      file_name = getattr(uploaded_file, 'filename', None)
      file_content = getattr(uploaded_file, 'file', None)
      mimetype = self.request.POST['uploaded_file'].type
      img_format = mimetype.split('/')[1]

      if (img_format == 'jpeg' or 'jpg' or 'gif' or 'png' or 'bmp' or 'tiff' or 'ico' or 'webp'):
        print 'img_format', img_format
      else:
        print 'file not image', img_format
        print 'mimetype', mimetype
      

      real_path = ''
      if file_name and file_content:
        content_t = mimetypes.guess_type(file_name)[0]
        real_path = os.path.join('/', bucket_name, user.user_id(),
                                 file_name)
        with cloudstorage.open(real_path, 'w',
                               content_type=content_t, 
                               options={'x-goog-acl':'public-read'}) as f:


           f.write(file_content.read())
       
      self._create_note(user, file_name, real_path)
      print 'called self._create_note'

      
      logout_url = users.create_logout_url(self.request.uri)
      template_context = {
          'user': user.nickname(),
          'logout_url': logout_url,
      }

     
      self.response.out.write(
           self._render_template('main.html', template_context))
      print 'called self._reander'

  
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
    bucket_name = app_identity.get_default_gcs_bucket_name()
    content_t = mimetypes.guess_type(file_name)[0]
    real_path = os.path.join('/', bucket_name, user.user_id(), file_name)
    try:
       with cloudstorage.open(real_path, 'r') as f:
         self.response.headers.add_header('Content-Type', content_t)
         self.response.out.write(f.read())
    except cloudstorage.errors.NotFoundError:
       self.abort(404)

class ShrinkHandler(webapp2.RequestHandler):
  def _shrink_note(self, note):
    for file_key in note.files:
        file = file_key.get()
        try:
          with cloudstorage.open(file.full_path) as f:
            image = images.Image(f.read())
            image.resize(640)
            content_t = images_formats.get(str(image.format))
            try:
              new_image_data = image.execute_transforms()
            except images.BadImageError: 
              pass
            
          with cloudstorage.open(file.full_path, 'w',
                                 content_type=content_t) as f:
             f.write(new_image_data)
        except images.NotImageError, images.BadImageError:
          pass
   
  def post (self):
    if not 'X-AppEngine-TaskName' in self.request.headers:
      self.error(403)

    user_email = self.request.get('user_email')
    user = users.User(user_email)

    ancestor_key = ndb.Key("User", user.nickname())
    notes = Note.owner_query(ancestor_key).fetch()
    
    for note in notes:
      self._shrink_note(note)
    
    sender_address = "Notes Team <notes@totheclouds.net>"
    subject = "Shrink-resize images complete!"
    body = "We shrunk all the images attached to your notes!"
    mail.send_mail(sender_address, user_email, subject, body)

  def get(self):
    user = users.get_current_user()
    if user is None:
      login_url = users.create_login_url(self.request.uri)
      return self.redirect(login_url)

    taskqueue.add(url='/shrink',
                params={'user_email': user.email()})

    self.response.write('Task successfully added to the queue.')

class ShrinkCronJob(ShrinkHandler):
  def post(self):
    self.abort(405, headers=[('Allow', 'GET')])
  
  def get(self):
    if 'X-AppEngine-Cron' not in self.request.headers:
      self.error(403)

      notes = Notes.query().fetch()
      for note in notes:
        self._shrink_note(note) 

    #ancestor_key = ndb.Key("User", user.nickname())
    #notes = Note.owner_query(ancestor_key).fetch()
 
    #for note in notes:
    #    self._shrink_note(note)                               
    #self.response.write('Done')

class CreateNoteHandler(mail_handlers.InboundMailHandler):
  def receive(self, mail_message):
    print mail_message.sender
    print mail_message
    print 'receive method called', mail_message
    email_pattern = re.compile(
      r'([\w\-\.]+@(\w[\w\-]+\.)+[\w\-]+)')

    print 'email_pattern', email_pattern
    match = email_pattern.findall(mail_message.sender)
    print 'match', match
    print match[0][0]
    email_addr = match[0][0] if match else ''

    print 'email_addr', email_addr
    try:
      user = users.User(email_addr)
      #user = self._reload_user(user)

    except users.UserNotFoundError:
      return self.error(403)

    title = mail_message.subject
    content = ''
    for content_t, body in mail_message.bodies('text/plain'):
      content += body.decode()


    attachments = getattr(mail_message, 'attachments', None)
    
    self._create_note(user, title, content, attachments)
    print "CreateNoteHandler"

  @ndb.transactional
  def _create_note(self, user, title, content, attachments):
  
    note = Note(parent=ndb.Key("User", user.nickname()),
                               title=title,
                               content=content)

    note.put()

    if attachments:
      bucket_name = app_identity.get_default_gcs_bucket_name()
      for file_name, file_content in attachments:
        content_t = mimetypes.guess_type(file_name)[0]
        real_path = os.path.join('/', bucket_name,
                               user.user_id(), file_name)
      
        with cloudstorage.open(real_path, 'w',
               content_type=content_t,
               options={'x-google-acl': 'public-read'}) as f:
          f.write(file_content.decode())

        key = blobstore.create_gs_key('/gs' + real_path)
        try:
           url = images.get_serving_url(key, size=0)
           thumbnail_url = images.get_serving_url(key, size=150, crop=True)
        except images.TransformationError, images.NotImageError:
          url = "http://storage.googleapis.com{}".format(real_path)
          thumbnail_url = None
    
        f = NoteFile(parent=note.key, name=file_name,
                  url=url, thumbnail_url=thumbnail_url,
                  full_path=real_path)
        f.put()
        note.files.append(f.key)


  def _reload_user(self, user_instance):
    key = UserLoader(user=user_instance).put()
    key.delete(use_datastore=False)
    u_loader = UserLoader.query(
            UserLoader.user == user_instance).get()
    return UserLoader.user


app = webapp2.WSGIApplication([
    (r'/', MainHandler),
    (r'/media/(?P<file_name>[\w.]{0,256})', MediaHandler),
    (r'/shrink', ShrinkHandler),
    (r'/shrink_all', ShrinkCronJob),
    (r'/_ah/mail/.+', CreateNoteHandler)
], debug=True)

   
