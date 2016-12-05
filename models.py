from  google.appengine.ext import ndb

class ChecKListItem(ndb.Model):
  title = ndb.StringPoperty()
  checked = ndb.BooleanProperty(default=False)

class Note(ndb.Model):
  title = ndb.StringProperty()
  content = ndb.TextProperty(required=True)
  date_created = ndb.DateTimeProperty(auto_now_add=True)
  checklist_items = ndb.KeyProperty('CheckListItem', 
                                    repeated=True)


  @classmethod
  def owner_query(cls, parent_key):
      return cls.query(ancestor=parent_key).order(
           -cls.date_created)

