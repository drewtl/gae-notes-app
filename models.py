from  google.appengine.ext import ndb

class Note(ndb.Model):
  title = ndb.StringProperty()
  content = ndb.TextProperty(required=True)
  date_created = ndb.DateTimeProperty(auto_now_add=True)

  @classmethod
  def owner_query(cls, parent_key):
      return cls.query(ancesteor=parent_key).order(
           -cls.date_created)
