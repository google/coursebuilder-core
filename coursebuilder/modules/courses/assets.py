# Copyright 2015 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Display course outline on dashboard page."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import copy
import os
import urllib

import appengine_config
from common import crypto
from common import jinja_utils
from common import safe_dom
from controllers import sites
from models import courses
from models import models
from models import transforms
from modules.dashboard import dashboard
from modules.dashboard import utils as dashboard_utils
from tools import verify

TEMPLATE_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'courses', 'templates')


class Asset(object):
    def __init__(self, filename, overridden, edit_url):
        self.filename = filename
        self.edit_url = edit_url
        self.overridden = overridden

    @property
    def name(self):
        return self.filename

    @property
    def external_url(self):
        return urllib.quote(self.filename)


def _list_and_format_file_list(
    handler, title, subfolder, tab_name,
    links=False, upload=False, prefix=None, caption_if_empty='< none >',
    edit_url_template=None, merge_local_files=False,
    all_paths=None):
    """Walks files in folders and renders their names in a section."""

    assets = []
    can_upload = upload and handler.app_context.is_editable_fs()

    upload_url = 'dashboard?{}'.format(urllib.urlencode({
        'action': 'manage_asset', 'from_action': handler.request.get('action'),
        'type': tab_name, 'key': subfolder}))

    # keep a list of files without merging
    unmerged_files = {}
    if merge_local_files:
        unmerged_files = dashboard_utils.list_files(
            handler.app_context, subfolder, all_paths=all_paths,
            merge_local_files=False)

    for filename in dashboard_utils.list_files(
            handler.app_context, subfolder, all_paths=all_paths,
            merge_local_files=merge_local_files):
        if prefix and not filename.startswith(prefix):
            continue

        overridden = (filename in unmerged_files) or (not merge_local_files)

        if edit_url_template and handler.app_context.fs.impl.is_read_write():
            edit_url = edit_url_template % (
                tab_name, urllib.quote(filename), handler.request.get('action'))
        else:
            edit_url = None

        assets.append(Asset(filename, overridden, edit_url))

    overridden_assets = [asset for asset in assets if asset.overridden]
    inherited_assets = [asset for asset in assets if not asset.overridden]

    return safe_dom.Template(
        jinja_utils.get_template('asset_list.html', [TEMPLATE_DIR]),
        inherited_assets=inherited_assets, overridden_assets=overridden_assets,
        can_upload=can_upload, caption_if_empty=caption_if_empty,
        upload_url=upload_url, links=links)

def _get_filter_data(handler):
    course = courses.Course(handler)
    unit_list = []
    assessment_list = []
    for unit in course.get_units():
        if verify.UNIT_TYPE_UNIT == unit.type:
            unit_list.append((unit.unit_id, unit.title))
        if unit.is_assessment():
            assessment_list.append((unit.unit_id, unit.title))

    lessons_map = {}
    for (unit_id, unused_title) in unit_list:
        lessons_map[unit_id] = [
            (l.lesson_id, l.title) for l in course.get_lessons(unit_id)]

    return {
        'data-units': transforms.dumps(unit_list + assessment_list),
        'data-lessons-map': transforms.dumps(lessons_map),
        'data-questions': transforms.dumps(
            [(question.id, question.description) for question in sorted(
                models.QuestionDAO.get_all(), key=lambda q: q.description)]
        ),
        'data-groups': transforms.dumps(
            [(group.id, group.description) for group in sorted(
                models.QuestionGroupDAO.get_all(), key=lambda g: g.description)]
        ),
        'data-types': transforms.dumps([
            (models.QuestionDTO.MULTIPLE_CHOICE, 'Multiple Choice'),
            (models.QuestionDTO.SHORT_ANSWER, 'Short Answer')])
    }

def _get_question_locations(quid, location_maps, used_by_groups):
    """Calculates the locations of a question and its containing groups."""
    (qulocations_map, qglocations_map) = location_maps
    locations = qulocations_map.get(quid, None)
    if locations is None:
        locations = {'lessons': {}, 'assessments': {}}
    else:
        locations = copy.deepcopy(locations)
    # At this point locations holds counts of the number of times quid
    # appears in each lesson and assessment. Now adjust the counts by
    # counting the number of times quid appears in a question group in that
    # lesson or assessment.
    lessons = locations['lessons']
    assessments = locations['assessments']
    for group in used_by_groups:
        qglocations = qglocations_map.get(group.id, None)
        if not qglocations:
            continue
        for lesson in qglocations['lessons']:
            lessons[lesson] = lessons.get(lesson, 0) + 1
        for assessment in qglocations['assessments']:
            assessments[assessment] = assessments.get(assessment, 0) + 1

    return locations

def _list_questions(handler, all_questions, all_question_groups, location_maps):
    """Prepare a list of the question bank contents."""
    if not handler.app_context.is_editable_fs():
        return safe_dom.NodeList()

    table_attributes = _get_filter_data(handler)
    table_attributes.update({
        'data-clone-question-token':
            crypto.XsrfTokenManager.create_xsrf_token('clone_question'),
        'data-qg-xsrf-token':
            crypto.XsrfTokenManager.create_xsrf_token('add_to_question_group'),
    })

    question_to_group = {}
    for group in all_question_groups:
        for quid in group.question_ids:
            question_to_group.setdefault(long(quid), []).append(group)

    question_infos = []

    for question in all_questions:
        # containing question groups
        used_by_groups = question_to_group.get(question.id, [])
        in_group_descriptions = sorted([
            group.description for group in used_by_groups])

        # locations
        locations = _get_question_locations(
            question.id, location_maps, used_by_groups)

        # type
        question_type = (
            'MC' if question.type == models.QuestionDTO.MULTIPLE_CHOICE else (
            'SA' if question.type == models.QuestionDTO.SHORT_ANSWER else (
            'Unknown Type')))

        # filter information
        filter_info = {}
        filter_info['description'] = question.description
        filter_info['type'] = question.type
        filter_info['lessons'] = []
        unit_ids = set()
        for (lesson, unit) in locations.get('lessons', ()):
            unit_ids.add(unit.unit_id)
            filter_info['lessons'].append(lesson.lesson_id)
        filter_info['units'] = list(unit_ids) + [
            a.unit_id for a in  locations.get('assessments', ())]
        filter_info['groups'] = [qg.id for qg in used_by_groups]
        filter_info['unused'] = int(not (locations and any(locations.values())))

        question_infos.append(dict(
            description=question.description,
            filter_info=transforms.dumps(filter_info),
            id=question.id,
            group_descriptions=in_group_descriptions,
            last_modified=question.last_modified,
            type=question_type,
            locations=locations,
            url='dashboard?action=edit_question&key=%s' % question.id,
        ))

    return safe_dom.Template(
        jinja_utils.get_template('question_list.html', [TEMPLATE_DIR]),
        table_attributes=table_attributes,
        groups_exist=bool(all_question_groups), questions=question_infos)


def _list_question_groups(
    handler, all_questions, all_question_groups, locations_map):
    """Prepare a list of question groups."""
    if not handler.app_context.is_editable_fs():
        return safe_dom.NodeList()

    question_group_infos = []
    quid_to_question = {long(qu.id): qu for qu in all_questions}
    for question_group in all_question_groups:
        url = 'dashboard?action=edit_question_group&key=%s' % (
            question_group.id)

        question_descriptions = sorted([
            quid_to_question[long(quid)].description
            for quid in question_group.question_ids])

        locations = locations_map.get(question_group.id, {})

        question_group_infos.append(dict(
            description=question_group.description,
            id=question_group.id, locations=locations,
            last_modified=question_group.last_modified,
            question_descriptions=question_descriptions, url=url))

    return safe_dom.Template(
        jinja_utils.get_template('question_group_list.html', [TEMPLATE_DIR]),
        question_groups=question_group_infos)

def _list_labels(handler, items, name, all_paths):
    """Prepare a list of labels for use on the Assets page."""
    if not handler.app_context.is_editable_fs():
        return safe_dom.NodeList()

    labels = sorted(
        models.LabelDAO.get_all_of_type(models.LabelDTO.LABEL_TYPE_GENERAL),
        key=lambda label: label.title)

    items.append(safe_dom.Template(
        jinja_utils.get_template('label_list.html', [TEMPLATE_DIR]),
        add_text='Add Label', add_action='add_label', edit_action='edit_label',
        items=labels))

def _list_tracks(handler, items, name, all_paths):
    """Prepare a list of labels for use on the Assets page."""
    if not handler.app_context.is_editable_fs():
        return safe_dom.NodeList()

    tracks = sorted(
        models.LabelDAO.get_all_of_type(
            models.LabelDTO.LABEL_TYPE_COURSE_TRACK),
        key=lambda label: label.title)

    items.append(safe_dom.Template(
        jinja_utils.get_template('label_list.html', [TEMPLATE_DIR]),
        add_text='Add Track', add_action='add_track', edit_action='edit_track',
        items=tracks))

def _filer_url_template():
    return 'dashboard?action=manage_text_asset&type=%s&uri=%s&from_action=%s'

def _get_assets_questions(handler, items, name, all_paths):
    all_questions = models.QuestionDAO.get_all()
    all_question_groups = models.QuestionGroupDAO.get_all()
    locations = courses.Course(handler).get_component_locations()
    items.append(_list_questions(
        handler, all_questions, all_question_groups, locations))

def _get_assets_question_groups(handler, items, name, all_paths):
    all_questions = models.QuestionDAO.get_all()
    all_question_groups = models.QuestionGroupDAO.get_all()
    locations = courses.Course(handler).get_component_locations()
    items.append(_list_question_groups(
        handler, all_questions, all_question_groups, locations[1]))

def _get_assets_assessments(handler, items, name, all_paths):
    items.append(_list_and_format_file_list(
        handler, 'Assessments', '/assets/js/', name, links=True,
        prefix='assets/js/assessment-', all_paths=all_paths))

def _get_assets_activities(handler, items, name, all_paths):
    items.append(_list_and_format_file_list(
        handler, 'Activities', '/assets/js/', name, links=True,
        prefix='assets/js/activity-', all_paths=all_paths))

def _get_assets_images(handler, items, name, all_paths):
    items.append(_list_and_format_file_list(
        handler, 'Images', '/assets/img/', name, links=True,
        upload=True, merge_local_files=True,
        edit_url_template=(
            'dashboard?action=manage_asset&type=%s&key=%s&from_action=%s'),
        caption_if_empty='< inherited from /assets/img/ >',
        all_paths=all_paths))

def _get_assets_css(handler, items, name, all_paths):
    items.append(_list_and_format_file_list(
        handler, 'CSS', '/assets/css/', name, links=True,
        upload=True, edit_url_template=_filer_url_template(),
        caption_if_empty='< inherited from /assets/css/ >',
        merge_local_files=True, all_paths=all_paths))

def _get_assets_js(handler, items, name, all_paths):
    items.append(_list_and_format_file_list(
        handler, 'JavaScript', '/assets/lib/', name, links=True,
        upload=True, edit_url_template=_filer_url_template(),
        caption_if_empty='< inherited from /assets/lib/ >',
        merge_local_files=True, all_paths=all_paths))

def _get_assets_html(handler, items, name, all_paths):
    items.append(_list_and_format_file_list(
        handler, 'HTML', '/assets/html/', name, links=True,
        upload=True, edit_url_template=_filer_url_template(),
        caption_if_empty='< inherited from /assets/html/ >',
        merge_local_files=True, all_paths=all_paths))

def _get_assets_templates(handler, items, name, all_paths):
    items.append(_list_and_format_file_list(
        handler, 'View Templates', '/views/', name, upload=True,
        edit_url_template=_filer_url_template(),
        caption_if_empty='< inherited from /views/ >',
        merge_local_files=True, all_paths=all_paths))

def _get_tab_content(tab, handler, add_assets):
    """Renders course assets view."""

    all_paths = handler.app_context.fs.list(
        sites.abspath(handler.app_context.get_home_folder(), '/'))
    items = safe_dom.NodeList()
    add_assets(handler, items, tab.name, all_paths)
    title_text = 'Assets > %s' % tab.title
    template_values = {
        'page_title': handler.format_title(title_text),
        'main_content': items,
    }
    return template_values

def _get_tab(handler, add_assets):
    tab = dashboard.DashboardHandler.actions_to_menu_items[
        handler.request.get('action')]
    return _get_tab_content(tab, handler, add_assets)

def can_view_assessments(app_context):
    return app_context and not courses.has_only_new_style_assessments(
        courses.Course(None, app_context=app_context))

def can_view_activities(app_context):
    return app_context and not courses.has_only_new_style_activities(
        courses.Course(None, app_context=app_context))

def on_module_enabled():
    # Content tabs
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'edit', 'questions', 'Questions', action='edit_questions',
        contents=lambda h: _get_tab(h, _get_assets_questions),
        placement=2000, sub_group_name='pinned')
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'edit', 'groups', 'Question Groups', action='edit_question_groups',
        contents=lambda h: _get_tab(h, _get_assets_question_groups),
        placement=2001, sub_group_name='pinned')
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'edit', 'html', 'HTML', action='edit_html',
        contents=lambda h: _get_tab(h, _get_assets_html))
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'edit', 'images', 'Images', action='edit_images',
        contents=lambda h: _get_tab(h, _get_assets_images))
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'edit', 'labels', 'Labels', action='edit_labels',
        contents=lambda h: _get_tab(h, _list_labels))
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'edit', 'tracks', 'Tracks', action='edit_tracks',
        contents=lambda h: _get_tab(h, _list_tracks))
    # These tabs only show up if your schema is old
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'edit', 'assessments', 'Assessments', action='edit_assessments',
        contents=lambda h: _get_tab(h, _get_assets_assessments),
        can_view=can_view_assessments)
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'edit', 'activities', 'Activities', action='edit_activities',
        contents=lambda h: _get_tab(h, _get_assets_activities),
        can_view=can_view_activities)

    # Style tabs
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'style', 'css', 'CSS', action='style_css',
        contents=lambda h: _get_tab(h, _get_assets_css))
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'style', 'js', 'JavaScript', action='style_js',
        contents=lambda h: _get_tab(h, _get_assets_js))
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'style', 'templates', 'Templates', action='style_templates',
        contents=lambda h: _get_tab(h, _get_assets_templates))
