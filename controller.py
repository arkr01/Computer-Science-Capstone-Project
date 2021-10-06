import pytz
from flask import Flask, request, render_template, redirect, url_for, abort, flash, Response, jsonify
from flask_login import login_required, current_user
import json
import random
import warnings
import os
from flask_login import LoginManager, login_required, login_user, logout_user, current_user, AnonymousUserMixin
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException, InternalServerError
from re import search as re_search
# If in branch use the following
from .DBFunc import *
from .forms import LoginForm, RegisterForm, ResourceForm
# If in main use the following
# from DBFunc import *
# from forms import LoginForm, RegisterForm, ResourceForm

# -----{ INIT }----------------------------------------------------------------
DEBUG = True

app = Flask(__name__)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "You need to be logged in to view this page"
login_manager.login_message_category = "error"

# NOTE: added for flush() usage
app.secret_key = "admin"

# File upload
app.config['UPLOAD_FOLDER'] = 'static/files/'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16 MB
app.config['MAX_CONTENT_PATH'] = 50 # 50 chars long
# -----{ LOGIN }---------------------------------------------------------------

class Anonymous(AnonymousUserMixin):
    def __init__(self):
        self.uid = -1
        self.username = "Guest User"

    def __str__(self):
        return f"Anonymous User: uid = {self.uid}"

    def __repr__(self):
        return __str__(self)

login_manager.anonymous_user = Anonymous


@login_manager.user_loader
def load_user(user_id):
    """
        :param unicode user_id: user_id (email) user to retrieve
    """
    return get_user(user_id)

# -----{ PAGES }---------------------------------------------------------------
#
# This section contains the different landing pages for the web page
#
# -----{ PAGES.MAIN }----------------------------------------------------------
@app.route('/')
def index():
    """The index root directory of this website
    Redirects to the home page
    """
    return redirect(url_for('home'))


@app.route('/home')
def home():
    """The home page of the website
    Shows recomendations based on the user profile or if not authenticated the
    most upvoted

    Also the end point of the search function where the search is a get method
    """

    return render_template('home.html', title='Home')

# -----{ PAGES.LOGIN }---------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page for a user to authenticate

    Asks for the users email and password.

    Gives feedback on fail, redirects to referring page on success
     (through GET data), if not refered then home page
    """
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        if email:
            user = get_user(email)
            if user != ErrorCode.INVALID_USER and check_password_hash(user.hash_password, form.password.data):
                user_auth(user.email,True)
                login_user(user, remember=True)
                if request.args.get("next"):
                    return redirect(request.args.get("next"))
                return redirect(url_for('home'))
        flash('That username or password was incorrect',"error")
    return render_template('login.html', title='Login',form=form)

@app.route('/logout')
@login_required
def logout():
    """Logout page
    Redircts in 3 seconds
    """
    user_auth(current_user.email,False)
    logout_user()
    flash('You have been logged out. This page will redirect in 3 seconds',"info")
    return render_template("logout.html",title='Logout')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Page for a user to register for an account

    Must provide: username, email, password (with conditions)

    Optionally provide: interests / subjects tags

    Other user fields are configured in profile()
    """
    data = {
        "username" : False,
        "emailUsed" : False,
        "passwordMsg" : False,
        "passwordDif" : False
        }
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data
        if email:
            user = get_user(email)
            # Ensure new account
            if user != ErrorCode.INVALID_USER:
                data['emailUsed'] = 'An account with that email already exists'
                # flash('An account with that email already exists',"error")
                return render_template('register.html', title='Register',form=form,data=data)
            # email validation
            if re_search('@',email) is None:
                data["emailUsed"] = "You must provide a valid email"
            username = form.username.data
            if not username:
                 data['username'] = 'You must provide a username'
            password = form.password.data
            passwordConfirm = form.passwordConfirm.data
            # Check passwords
            if not password or not passwordConfirm:
                data['passwordMsg'] = 'You must provide a valid password'
            if password != passwordConfirm:
                data['passwordDif'] = True
            if len(password) < 8:
                data['passwordMsg'] = "Make sure your password is at lest 8 letters"
            elif re_search('[0-9]',password) is None:
                data['passwordMsg'] = "Make sure your password has a number in it"
            elif re_search('[A-Z]',password) is None:
                data['passwordMsg'] = "Make sure your password has a capital letter in it"
            else:
                # add user and log in
                res = add_user(username,password,email)
                if res != ErrorCode.COMMIT_ERROR:
                    user = get_user(email)
                    user_auth(user.email,True)
                    login_user(user, remember=True)
                    # return redirect(url_for('home'))
                flash('Something went wrong, please try again',"error")
        else:
            data['emailUsed'] = 'You must provide a valid email'
    return render_template('register.html', title='Register',form=form,data=data)

# -----{ PAGES.RESOURCE }------------------------------------------------------

@app.route('/resource')
@app.route('/resource/<int:rid>', methods=["GET", "POST"])
def resource(rid=None):
    """Page for a resource

    If no resource ID is set then the home page is shown
    If a resource ID is set then that resource page is shown

    Shows information based on the resource type and content

    :param rid: The resource id

    If the currently logged in user does not have access to the resource then
    they are given a 403
    If the resource does not exist then they are given a 404
    """
    # Base resource page
    if rid is None:
        return render_template('resource.html', title='Resources')
    uid = current_user.uid
    # individual resource page
    user, res = get_user_and_resource_instance(uid=uid, rid=rid)
    # resource does not exist
    if res is None:
        abort(404,description="The requested resource does not exist")
    # user has access to resource
    if not is_resource_public(rid=rid) and (user is None or not user_has_access_to_resource(uid=uid, rid=rid)):
        abort(403,description=f"You ({current_user.username}) do not have permission to access the resource : {res.title}" + "\nIf you think this is incorrect contact the resource owner")

    # User has requested a page with HTML GET
    if request.method == "GET":
        # show resource detail

        # convert to human readable form
        subject = enum_to_website_output(res.subject)
        grade = enum_to_website_output(res.grade)
        difficulty = enum_to_website_output(res.difficulty)

        # convert utc time to AEST
        created_at = res.created_at.astimezone(pytz.timezone("Australia/Brisbane"))

        # get a list of resource_comment objects
        resource_comment_list = get_resource_comments(rid=rid)
        # get a dict of resource_comment instance -> resource_comment_replies instances to that comment
        resource_comment_replies_list = get_resource_comment_replies(resource_comment_list)
        resource_tags = get_resource_tags(res.rid)
        return render_template("resource_item.html", rid=rid, uid=uid,
                               res=res, difficulty=difficulty, subject=subject, grade=grade,resource_tags=resource_tags)
    # User has requested a page with HTML GET
    elif request.method == "POST":
        # FIXME: here assume upvote and downvote are two separate buttons like Quora
        # example see https://predictivehacks.com/?all-tips=how-to-add-action-buttons-in-flask
        # update do upvote/downvote
        up, down = request.form.get("upvote"), request.form.get("downvote")
        vote_res = vote_resource(uid=uid, rid=rid, upvote=up is not None)
        if vote_res == ErrorCode.SAME_VOTE_TWICE:
            # the user voted the same vote twice
            # todo: here I do flash message, you can modify it
            flash("Oh please don't vote the same thing twice, will ya?","info")

        # reach here a vote is made or vote is invalid, now refresh resource page
        return redirect(url_for("resource", uid=uid, rid=rid))
    return render_template('base.html', title='Register')


@app.route('/resourceAJAX')
def resourceAJAX():
    """The endpoint for the AJAX search for resources using a get request
    returns it in json format
    """
    title = request.args.get('title') if 'title' in request.args else None
    subject = request.args.get('subject').upper() if 'subject' in request.args else None
    year = request.args.get('year').upper() if 'year' in request.args else None
    tags = str(request.args.getlist('tags[]')) if 'tags[]' in request.args else None
    try:
        subject = Subject[subject]
    except KeyError:
        subject = None
    try:
        year = Grade[year]
    except KeyError:
        year = None
    if title == '':
        title = None
    return jsonify([dict(i.serialize,tags=get_resource_tags(i.rid)) for i in find_resources(title=title,subject=subject,grade=year,tags=tags)])


@app.route('/resource/new', methods=['GET', 'POST'])
def resource_new():
    """The user creates a new resource
    """
    form = ResourceForm()
    if form.validate_on_submit():
        if form.files.data:
            f = request.files[form.files.name]
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(f.filename)))
            flash("File was uploaded",'info')
    return render_template('resource_create.html', title='New Resource',form=form)
    # todo

# -----{ PAGES.PROFILE }-------------------------------------------------------

@app.route('/profile')
@login_required
def profile():
    """The default view of a users profile,
    this can be used to view your own or other users profiles.
    Specified with the GET request
    /profile?<id / name>

    Shows the following content:
        Liked resources
        Created resources
        Your reviews / comments

    Additional options are available if viewing your own profile:
        Manage account settings
        Forums you are a part of
    """

    return render_template('profile.html', title='Profile')


@app.route('/profile/settings')
def settings():
    """The user configuration page,
    allows the user to edit their:
        Bio.
        Email.
        Password.
        Avatar.
        Interests
    """
    return render_template('base.html', title='Login')

# -----{ PAGES.GENERIC }-------------------------------------------------------

@app.route('/about')
def about():
    """A brief page describing what the website is about"""
    return render_template('about.html', title='About Us', name="About Us")

# -----{ PAGES.CHANNELS }-------------------------------------------------------

@app.route('/create')
@app.route('/create/<type>')
def create(type=None):
    """The user create a resource or channel
    If type is not resource or channel redirect to home
    If type == None then prompt the user to select which create type they want
    and redirect to that page
    Create Channel
    Allows the user to give a title, desc., tags
    Create resource
    Allows the user to give a title, desc., tags, upload content, link to similar
    """
    return render_template('base.html', title='Post')

@app.route('/channel')
@app.route('/channel/<fName>/<tName>')
@app.route('/channel/<fName>')
def channel(fName=None, tName=None):
    """The user view a forum page
    The home forum page (fName == None, tName == None) shows the list of forums
    Allows user to create a channel etc.
    The forum/fName page shows the threads in that forum
    Allows users to add threads to the forum
    The forum/fName/tName shows the thread on that forum.
    Allows users to add comments to the forum post
    The forum/fName/tName?<id> shows the comment on that forum page or the top
    of page if not valid.
    If fName is not valid name redirect to home forum page
    If tName is not valid redirect to forum page
    """
    if (fName is not None and tName is None):
        return render_template('channel_item.html',
                               title='Channels',
                               subject=[enum_to_website_output(e) for e in Subject],
                               grade=[enum_to_website_output(e) for e in Grade],
                               tag=get_tags().keys(),
                               resources=find_resources())
    if fName is None or tName is None:
        return render_template('channel.html',
                               title='Channels',
                               subject=[enum_to_website_output(e) for e in Subject],
                               grade=[enum_to_website_output(e) for e in Grade],
                               tag=get_tags().keys(),
                               resources=find_resources())


    return render_template('channel.html', title='Post')


@app.route("/channel/comment/<post_id>")
@login_required
def comment_channel_post(post_id):
    """
    Use this to add a comment to a post

    If post_id is not valid then redirect to post page
    """
    # todo
    return render_template('base.html', title='Post')


# -----{ PAGES.DEBUG }---------------------------------------------------------

@app.route('/debug')
def debug():
    """A debugging page
    not to be used in production
    """
    return render_template('debug.html', title='DEBUG',variable=None)


# -----{ ERRORS }--------------------------------------------------------------

@app.errorhandler(Exception)
def handle_exception(e):
    # pass through HTTP errors
    if isinstance(e, HTTPException):
        return render_template("errors/error_generic.html", e=e), e.code

    # non-HTTP exceptions default to 500
    if DEBUG:
        return render_template("errors/error_generic.html", e=InternalServerError(),fail=e), 500
    return render_template("errors/error_generic.html", e=InternalServerError()), 500


# -----{ PROCESSORS }----------------------------------------------------------

@app.context_processor
def subject_processor():
    def enum_to_website_output(item: str) -> str:
        return item.replace('_', ' ', 1).title()
    return dict(enum_to_website_output=enum_to_website_output)

@app.context_processor
def defaults():
    """Provides the default context processors

    Returns:
        dict: Variables for JINJA context
            current_user: the user the is currently logged in or the Anonymous user
            subject : A list of all subjects with their names
            grade : A list of all grades with their names
            tag : A list of all tags with their names
    """
    return dict(current_user=current_user,
                subjects=[e.name.lower() for e in Subject],
                grades=[e.name.lower() for e in Grade],
                tags=[e.replace(' ','_').replace('-','_') for e in get_tags().keys()])