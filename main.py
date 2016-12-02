import webapp2
import os
import jinja2

from google.appengine.api import users

jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))

class MainHandler(webapp2.RequestHandler):
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


app = webapp2.WSGIApplication([
    ('/', MainHandler)
], debug=True)
