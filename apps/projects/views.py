import logging

from django import http
from django.conf import settings
from django.core.urlresolvers import reverse
from django.shortcuts import render_to_response, get_object_or_404
from django.http import HttpResponseRedirect 
from django.template import RequestContext
from django.utils import simplejson
from django.utils.translation import ugettext as _
from django.views.decorators.http import require_http_methods

from commonware.decorators import xframe_sameorigin

from projects import forms as project_forms
from projects.decorators import ownership_required
from projects.models import Project, ProjectMedia

from relationships.models import Relationship
from links.models import Link
from users.models import UserProfile
from content.models import Page

from drumbeat import messages
from users.decorators import login_required

log = logging.getLogger(__name__)


def show(request, slug):
    project = get_object_or_404(Project, slug=slug)
    context = {
        'project': project,
        'activities': project.activities()[0:10],
    }
    return render_to_response('projects/project.html', context,
                          context_instance=RequestContext(request))


@login_required
@ownership_required
def edit(request, slug):
    project = get_object_or_404(Project, slug=slug)
    if request.method == 'POST':
        form = project_forms.ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            messages.success(request, _('Course updated!'))
            return http.HttpResponseRedirect(
                reverse('projects_edit', kwargs=dict(slug=project.slug)))
    else:
        form = project_forms.ProjectForm(instance=project)

    return render_to_response('projects/project_edit_summary.html', {
        'form': form,
        'project': project,
    }, context_instance=RequestContext(request))


@login_required
@xframe_sameorigin
@ownership_required
@require_http_methods(['POST'])
def edit_image_async(request, slug):
    project = get_object_or_404(Project, slug=slug)
    form = project_forms.ProjectImageForm(request.POST, request.FILES,
                                          instance=project)
    if form.is_valid():
        instance = form.save()
        return http.HttpResponse(simplejson.dumps({
            'filename': instance.image.name,
        }))
    return http.HttpResponse(simplejson.dumps({
        'error': 'There was an error uploading your image.',
    }))


@login_required
@ownership_required
def edit_image(request, slug):
    project = get_object_or_404(Project, slug=slug)
    if request.method == 'POST':
        form = project_forms.ProjectImageForm(request.POST, request.FILES,
                                              instance=project)
        if form.is_valid():
            messages.success(request, _('Image updated'))
            form.save()
            return http.HttpResponseRedirect(reverse('projects_show', kwargs={
                'slug': project.slug,
            }))
        else:
            messages.error(request,
                           _('There was an error uploading your image'))
    else:
        form = project_forms.ProjectImageForm(instance=project)
    return render_to_response('projects/project_edit_image.html', {
        'project': project,
        'form': form,
    }, context_instance=RequestContext(request))


@login_required
@ownership_required
def edit_links(request, slug):
    project = get_object_or_404(Project, slug=slug)
    if request.method == 'POST':
        form = project_forms.ProjectLinksForm(request.POST)
        if form.is_valid():
            link = form.save(commit=False)
            link.project = project
            link.user = project.created_by
            link.save()
            messages.success(request, _('Link added.'))
            return http.HttpResponseRedirect(
                reverse('projects_edit_links', kwargs=dict(slug=project.slug)))
        else:
            messages.error(request, _('There was an error adding your link.'))
    else:
        form = project_forms.ProjectLinksForm()
    links = Link.objects.select_related('subscription').filter(project=project)
    return render_to_response('projects/project_edit_links.html', {
        'project': project,
        'form': form,
        'links': links,
    }, context_instance=RequestContext(request))

@login_required
@ownership_required
def edit_followers(request, slug):
    project = get_object_or_404(Project, slug=slug)
    followers = project.followers()
    return render_to_response('projects/project_edit_followers.html', {
        'project': project,
        'followers': followers
    }, context_instance=RequestContext(request))

@login_required
@ownership_required
def add_follower(request, slug):
    project = get_object_or_404(Project, slug=slug)
    if request.method == 'POST' and 'username' in request.POST:
        username = request.POST['username']
        user = UserProfile.objects.filter(username=username)[0]
        if not user:
            messages.error(
                request, _('Username %s does not exist' % username))
        else:
            new_rel = Relationship(source=user, target_project=project)
            try:
                new_rel.save()
            except IntegrityError: 
                messages.error(
                    request, _('You are already following this course'))
    return HttpResponseRedirect(request.META['HTTP_REFERER'])

@login_required
@ownership_required
def delete_follower(request, slug):
    project = get_object_or_404(Project, slug=slug)
    # TODO should use a proper django form for this?
    if request.method == 'POST' and 'follower_id' in request.POST:
        follower_id = int(request.POST['follower_id'])
        follower = UserProfile.objects.get(id=follower_id)
        # use filter() instead of get() to return None instead of raise an
        # error for objects that do not exist. 
        rel = Relationship.objects.filter(
            source=follower, target_project=project
        )[0]
        if project.created_by == follower:
            messages.error(request, _(
                "You cannot unfollow your own course" ))
        elif rel :
            rel.delete()
            messages.success(request, _(
                "The follower %s has been removed." % follower.display_name))
        else:
            messages.error(request, _(
                "The user is not following this course"))
    else:
        messages.error(request, _(
            "There was an error removing the user."))
    return http.HttpResponseRedirect(reverse('projects_edit_followers', kwargs={
        'slug': project.slug,
    }))        

@login_required
@ownership_required
def edit_links_delete(request, slug, link):
    if request.method == 'POST':
        project = get_object_or_404(Project, slug=slug)
        link = get_object_or_404(Link, pk=link)
        if link.project != project:
            return http.HttpResponseForbidden()
        link.delete()
        messages.success(request, _('The link was deleted'))
    return http.HttpResponseRedirect(
        reverse('projects_edit_links', kwargs=dict(slug=slug)))


def list(request):
    featured = Project.objects.filter(featured=True)
    new = Project.objects.all().order_by('-created_on')[:4]
    active = Project.objects.get_popular(limit=4)

    def assign_counts(projects):
        for project in projects:
            project.followers_count = Relationship.objects.filter(
                target_project=project).count()

    assign_counts(featured)
    assign_counts(new)
    assign_counts(active)

    return render_to_response('projects/gallery.html', {
        'featured': featured,
        'new': new,
        'active': active,
    }, context_instance=RequestContext(request))


@login_required
def create(request):
    user = request.user.get_profile()
    if request.method == 'POST':
        form = project_forms.ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.created_by = user
            project.save()
            detailed_description = Page(title='Full Description',
                content='<p>Please fill out.</p>', listed=False,
                author_id=user.id, project_id=project.id)
            detailed_description.save()
            project.detailed_description_id = detailed_description.id
            project.save()
            messages.success(request, _('Your new course has been created.'))
            return http.HttpResponseRedirect(reverse('projects_show', kwargs={
                'slug': project.slug,
            }))
        else:
            messages.error(request,
                _("There was a problem creating your course."))
    else:
        form = project_forms.ProjectForm()
    return render_to_response('projects/project_edit_summary.html', {
        'form': form,
    }, context_instance=RequestContext(request))


@login_required
def contact_followers(request, slug):
    user = request.user.get_profile()
    project = get_object_or_404(Project, slug=slug)
    if project.created_by != user:
        return http.HttpResponseForbidden()
    if request.method == 'POST':
        form = project_forms.ProjectContactUsersForm(request.POST)
        if form.is_valid():
            form.save(sender=request.user)
            messages.info(request,
                          _("Message successfully sent."))
            return http.HttpResponseRedirect(reverse('projects_show', kwargs={
                'slug': project.slug,
            }))
    else:
        form = project_forms.ProjectContactUsersForm()
        form.fields['project'].initial = project.pk
    return render_to_response('projects/contact_users.html', {
        'form': form,
        'project': project,
    }, context_instance=RequestContext(request))


@login_required
@ownership_required
def edit_preparation_status(request, slug):
    project = get_object_or_404(Project, slug=slug)
    if request.method == 'POST':
        form = project_forms.ProjectPreparationStatusForm(
            request.POST, instance=project)
        if form.is_valid():
            form.save()
            return http.HttpResponseRedirect(reverse('projects_show', kwargs={
                'slug': project.slug,
            }))
        else:
            messages.error(request,
                           _('There was a problem saving the preparation status.'))
    else:
        form = project_forms.ProjectPreparationStatusForm(instance=project)
    return render_to_response('projects/project_edit_preparation_status.html', {
        'form': form,
        'project': project,
    }, context_instance=RequestContext(request))

