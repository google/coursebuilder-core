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
from common import safe_dom
from controllers import sites
from models import courses
from models import models
from models import transforms
from modules.dashboard import dashboard
from modules.dashboard import utils as dashboard_utils
from tools import verify

# Other modules which manage editable assets can add functions here to
# list their assets on the Assets tab. The function will receive an instance
# of DashboardHandler as an argument.
contrib_asset_listers = []

TEMPLATE_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'courses', 'views')


def _list_and_format_file_list(
    handler, title, subfolder, tab_name,
    links=False, upload=False, prefix=None, caption_if_empty='< none >',
    edit_url_template=None, merge_local_files=False, sub_title=None,
    all_paths=None):
    """Walks files in folders and renders their names in a section."""

    # keep a list of files without merging
    unmerged_files = {}
    if merge_local_files:
        unmerged_files = dashboard_utils.list_files(
            handler, subfolder, merge_local_files=False, all_paths=all_paths)

    items = safe_dom.NodeList()
    count = 0
    for filename in dashboard_utils.list_files(
            handler, subfolder, merge_local_files=merge_local_files,
            all_paths=all_paths):
        if prefix and not filename.startswith(prefix):
            continue

        # make a <li> item
        li = safe_dom.Element('li')
        if links:
            url = urllib.quote(filename)
            li.add_child(safe_dom.Element(
                'a', href=url).add_text(filename))
        else:
            li.add_text(filename)

        # add actions if available
        if (edit_url_template and
            handler.app_context.fs.impl.is_read_write()):

            li.add_child(safe_dom.Entity('&nbsp;'))
            edit_url = edit_url_template % (
                tab_name, urllib.quote(filename), handler.request.get('action'))
            # show [overridden] + edit button if override exists
            if (filename in unmerged_files) or (not merge_local_files):
                li.add_text('[Overridden]').add_child(
                    dashboard_utils.create_edit_button(edit_url))
            # show an [override] link otherwise
            else:
                li.add_child(safe_dom.A(edit_url).add_text('[Override]'))

        count += 1
        items.append(li)

    output = safe_dom.NodeList()

    if handler.app_context.is_editable_fs() and upload:
        output.append(
            safe_dom.Element(
                'a', className='gcb-button gcb-icon-button',
                href='dashboard?%s' % urllib.urlencode(
                    {'action': 'manage_asset',
                     'from_action': handler.request.get('action'),
                     'type': tab_name,
                     'key': subfolder}),
                id='upload-button',
            ).append(
                safe_dom.Element('span', className='icon md-file-upload')
            ).append(
                safe_dom.Element('span').add_text(" Upload")
            )
        )
    if sub_title:
        output.append(safe_dom.Element(
            'div', className='gcb-message').add_text(sub_title))
    if items:
        output.append(safe_dom.Element('ol').add_children(items))
    else:
        if caption_if_empty:
            output.append(
                safe_dom.Element(
                    'div', className='gcb-message').add_text(caption_if_empty))
    return output

def _attach_filter_data(handler, element):
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

    element.add_attribute(
        data_units=transforms.dumps(unit_list + assessment_list),
        data_lessons_map=transforms.dumps(lessons_map),
        data_questions=transforms.dumps(
            [(question.id, question.description) for question in sorted(
                models.QuestionDAO.get_all(), key=lambda q: q.description)]
        ),
        data_groups=transforms.dumps(
            [(group.id, group.description) for group in sorted(
                models.QuestionGroupDAO.get_all(), key=lambda g: g.description)]
        ),
        data_types=transforms.dumps([
            (models.QuestionDTO.MULTIPLE_CHOICE, 'Multiple Choice'),
            (models.QuestionDTO.SHORT_ANSWER, 'Short Answer')])
    )

def _create_location_link(text, url, loc_id, count):
    return safe_dom.Element(
        'li', data_count=str(count), data_id=str(loc_id)).add_child(
        safe_dom.Element('a', href=url).add_text(text)).add_child(
        safe_dom.Element('span', className='count').add_text(
        ' (%s)' % count if count > 1 else ''))

def _create_locations_cell(locations):
    ul = safe_dom.Element('ul')
    for (assessment, count) in locations.get('assessments', {}).iteritems():
        ul.add_child(_create_location_link(
            assessment.title, 'assessment?name=%s' % assessment.unit_id,
            assessment.unit_id, count
        ))

    for ((lesson, unit), count) in locations.get('lessons', {}).iteritems():
        ul.add_child(_create_location_link(
            '%s: %s' % (unit.title, lesson.title),
            'unit?unit=%s&lesson=%s' % (unit.unit_id, lesson.lesson_id),
            lesson.lesson_id, count
        ))

    return safe_dom.Element('td', className='locations').add_child(ul)

def _create_list(list_items):
    ul = safe_dom.Element('ul')
    for item in list_items:
        ul.add_child(safe_dom.Element('li').add_child(item))
    return ul

def _create_list_cell(list_items):
    return safe_dom.Element('td').add_child(_create_list(list_items))

def _create_add_to_group_button():
    return safe_dom.Element(
        'div',
        className='icon md md-add-circle gcb-pull-right',
        title='Add to question group',
        alt='Add to question group'
    )

def _create_preview_button():
    return safe_dom.Element(
        'div',
        className='icon md md-visibility',
        title='Preview',
        alt='Preview'
    )

def _create_clone_button(question_id):
    return safe_dom.A(
        href='#',
        className='icon md md-content-copy',
        title='Clone',
        alt='Clone',
        data_key=str(question_id)
    )

def _add_assets_table(output, table_id, columns):
    """Creates an assets table with the specified columns.

    Args:
        output: safe_dom.NodeList to which the table should be appended.
        table_id: string specifying the id for the table
        columns: list of tuples that specifies column name and width.
            For example ("Description", 35) would create a column with a
            width of 35% and the header would be Description.

    Returns:
        The table safe_dom.Element of the created table.
    """
    container = safe_dom.Element('div', className='assets-table-container')
    output.append(container)
    table = safe_dom.Element('table', className='assets-table', id=table_id)
    container.add_child(table)
    thead = safe_dom.Element('thead')
    table.add_child(thead)
    tr = safe_dom.Element('tr')
    thead.add_child(tr)
    ths = safe_dom.NodeList()
    for (title, width) in columns:
        ths.append(safe_dom.Element(
            'th', style=('width: %s%%' % width)).add_text(title).add_child(
                safe_dom.Element(
                    'span', className='md md-arrow-drop-up')).add_child(
                safe_dom.Element(
                    'span', className='md md-arrow-drop-down')))
    tr.add_children(ths)
    return table

def _create_empty_footer(text, colspan, set_hidden=False):
    """Creates a <tfoot> that will be visible when the table is empty."""
    tfoot = safe_dom.Element('tfoot')
    if set_hidden:
        tfoot.add_attribute(style='display: none')
    empty_tr = safe_dom.Element('tr')
    return tfoot.add_child(empty_tr.add_child(safe_dom.Element(
        'td', colspan=str(colspan), style='text-align: center'
    ).add_text(text)))

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

    toolbar_template = handler.get_template(
        'question_toolbar.html', [TEMPLATE_DIR])
    toolbar_node = safe_dom.Template(toolbar_template,
        question_count=len(all_questions))

    output = safe_dom.NodeList().append(toolbar_node)

    # Create questions table
    table = _add_assets_table(
        output, 'question-table', [
        ('Description', 25), ('Question Groups', 25),
        ('Course Locations', 25), ('Last Modified', 16), ('Type', 9)]
    )
    _attach_filter_data(handler, table)
    token = crypto.XsrfTokenManager.create_xsrf_token('clone_question')
    table.add_attribute(data_clone_question_token=token)
    token = crypto.XsrfTokenManager.create_xsrf_token('add_to_question_group')
    table.add_attribute(data_qg_xsrf_token=token)
    tbody = safe_dom.Element('tbody')
    table.add_child(tbody)

    table.add_child(_create_empty_footer(
        'No questions available', 5, all_questions))

    question_to_group = {}
    for group in all_question_groups:
        for quid in group.question_ids:
            question_to_group.setdefault(long(quid), []).append(group)

    for question in all_questions:
        tr = safe_dom.Element('tr', data_quid=str(question.id))
        # Add description including action icons
        td = safe_dom.Element('td', className='description')
        tr.add_child(td)
        td.add_child(dashboard_utils.create_edit_button(
            'dashboard?action=edit_question&key=%s' % question.id))
        td.add_child(_create_preview_button())
        td.add_child(_create_clone_button(question.id))
        td.add_text(question.description)

        # Add containing question groups
        used_by_groups = question_to_group.get(question.id, [])
        cell = safe_dom.Element('td', className='groups')
        if all_question_groups:
            cell.add_child(_create_add_to_group_button())
        cell.add_child(_create_list(
            [safe_dom.Text(group.description) for group in sorted(
                used_by_groups, key=lambda g: g.description)]
        ))
        tr.add_child(cell)

        # Add locations
        locations = _get_question_locations(
            question.id, location_maps, used_by_groups)
        tr.add_child(_create_locations_cell(locations))

        # Add last modified timestamp
        tr.add_child(safe_dom.Element(
            'td',
            data_timestamp=str(question.last_modified),
            className='timestamp'
        ))

        # Add question type
        tr.add_child(safe_dom.Element('td').add_text(
            'MC' if question.type == models.QuestionDTO.MULTIPLE_CHOICE else (
                'SA' if question.type == models.QuestionDTO.SHORT_ANSWER else (
                'Unknown Type'))
        ).add_attribute(style='text-align: center'))

        # Add filter information
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
        tr.add_attribute(data_filter=transforms.dumps(filter_info))
        tbody.add_child(tr)

    return output

def _list_question_groups(
    handler, all_questions, all_question_groups, locations_map):
    """Prepare a list of question groups."""
    if not handler.app_context.is_editable_fs():
        return safe_dom.NodeList()

    output = safe_dom.NodeList()
    output.append(safe_dom.Element('h3').add_text(
        'Question Groups (%s)' % len(all_question_groups)
    ))
    output.append(
        safe_dom.Element(
            'div', className='gcb-button-toolbar'
        ).append(
            safe_dom.Element(
                'a', className='gcb-button',
                href='dashboard?action=add_question_group'
            ).add_text('Add Question Group')
        )
    ).append(
        safe_dom.Element(
            'div', style='clear: both; padding-top: 2px;'
        )
    )

    # Create question groups table
    table = _add_assets_table(
        output, 'question-group-table', [
        ('Description', 25), ('Questions', 25), ('Course Locations', 25),
        ('Last Modified', 25)]
    )
    tbody = safe_dom.Element('tbody')
    table.add_child(tbody)

    if not all_question_groups:
        table.add_child(_create_empty_footer(
            'No question groups available', 4))

    quid_to_question = {long(qu.id): qu for qu in all_questions}
    for question_group in all_question_groups:
        tr = safe_dom.Element('tr', data_qgid=str(question_group.id))
        # Add description including action icons
        td = safe_dom.Element('td', className='description')
        tr.add_child(td)
        td.add_child(dashboard_utils.create_edit_button(
            'dashboard?action=edit_question_group&key=%s' % (
            question_group.id)))
        td.add_text(question_group.description)

        # Add questions
        tr.add_child(_create_list_cell([
            safe_dom.Text(descr) for descr in sorted([
                quid_to_question[long(quid)].description
                for quid in question_group.question_ids])
        ]).add_attribute(className='questions'))

        # Add locations
        tr.add_child(_create_locations_cell(
            locations_map.get(question_group.id, {})))

        # Add last modified timestamp
        tr.add_child(safe_dom.Element(
            'td',
            data_timestamp=str(question_group.last_modified),
            className='timestamp'
        ))

        tbody.add_child(tr)

    return output

def _list_labels(handler):
    """Prepare a list of labels for use on the Assets page."""
    output = safe_dom.NodeList()
    if not handler.app_context.is_editable_fs():
        return output

    output.append(
        safe_dom.A('dashboard?action=add_label',
                   className='gcb-button'
                  ).add_text('Add Label')
        ).append(
            safe_dom.Element(
                'div', style='clear: both; padding-top: 2px;'
            )
        )
    labels = models.LabelDAO.get_all()
    if labels:
        all_labels_ul = safe_dom.Element('ul')
        output.append(all_labels_ul)
        for label_type in sorted(
            models.LabelDTO.LABEL_TYPES,
            lambda a, b: cmp(a.menu_order, b.menu_order)):

            type_li = safe_dom.Element('li').add_child(
                safe_dom.Element('strong').add_text(label_type.title))
            all_labels_ul.add_child(type_li)
            labels_of_type_ul = safe_dom.Element('ul')
            type_li.add_child(labels_of_type_ul)
            for label in sorted(
                labels, lambda a, b: cmp(a.title, b.title)):
                if label.type == label_type.type:
                    li = safe_dom.Element('li')
                    labels_of_type_ul.add_child(li)
                    li.add_text(
                        label.title
                    ).add_attribute(
                        title='id: %s, type: %s' % (label.id, label_type))
                    if label_type not in (
                        models.LabelDTO.SYSTEM_EDITABLE_LABEL_TYPES):

                        li.add_child(
                            dashboard_utils.create_edit_button(
                                'dashboard?action=edit_label&key=%s' %
                                label.id,
                                ).add_attribute(
                                    id='label_%s' % label.title))
    else:
        output.append(
            safe_dom.Element(
                'div', className='gcb-message').add_text('< none >'))
    return output


def _filer_url_template():
    return 'dashboard?action=manage_text_asset&type=%s&uri=%s&from_action=%s'

def _get_assets_questions(handler, items, name, all_paths):
    all_questions = models.QuestionDAO.get_all()
    all_question_groups = models.QuestionGroupDAO.get_all()
    locations = courses.Course(handler).get_component_locations()
    items.append(_list_questions(
        handler, all_questions, all_question_groups, locations))
    items.append(_list_question_groups(
        handler, all_questions, all_question_groups, locations[1]))

def _get_assets_labels(handler, items, name, all_paths):
    items.append(_list_labels(handler))

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
        handler, 'Images & documents', '/assets/img/', name, links=True,
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

def _get_assets_contrib(handler, items, name, all_paths):
    if not contrib_asset_listers:
        items.append(safe_dom.Text(
            'No assets extensions have been registered'))
    else:
        for asset_lister in contrib_asset_listers:
            items.append(asset_lister(handler))

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

def _get_style_tab(handler, add_assets):
    tab = dashboard.DashboardHandler.actions_to_menu_items[
        handler.request.get('action') or 'style_css']
    return _get_tab_content(tab, handler, add_assets)

def _get_edit_tab(handler, add_assets):
    tab = dashboard.DashboardHandler.actions_to_menu_items[
        handler.request.get('action') or 'edit_questions']
    return _get_tab_content(tab, handler, add_assets)

def can_view_assessments(app_context):
    return not courses.has_only_new_style_assessments(
        courses.Course(None, app_context=app_context))

def can_view_activities(app_context):
    return not courses.has_only_new_style_activities(
        courses.Course(None, app_context=app_context))

def on_module_enabled():
    # Content tabs
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'edit', 'questions', 'Questions', action='edit_questions',
        contents=lambda h: _get_edit_tab(h, _get_assets_questions),
        placement=2000)
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'edit', 'images', 'Images & documents', action='edit_images',
        contents=lambda h: _get_edit_tab(h, _get_assets_images),
        placement=6000)
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'edit', 'labels', 'Labels', action='edit_labels',
        contents=lambda h: _get_edit_tab(h, _get_assets_labels),
        placement=7000)

    # These tabs only show up if your schema is old
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'edit', 'assessments', 'Assessments', action='edit_assessments',
        contents=lambda h: _get_edit_tab(h, _get_assets_assessments),
        can_view=can_view_assessments)
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'edit', 'activities', 'Activities', action='edit_activities',
        contents=lambda h: _get_edit_tab(h, _get_assets_activities),
        can_view=can_view_activities)

    # Style tabs
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'style', 'css', 'CSS', action='style_css',
        contents=lambda h: _get_style_tab(h, _get_assets_css),
        placement=1000)
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'style', 'js', 'JavaScript', action='style_js',
        contents=lambda h: _get_style_tab(h, _get_assets_js),
        placement=2000)
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'style', 'html', 'HTML', action='style_html',
        contents=lambda h: _get_style_tab(h, _get_assets_html),
        placement=3000)
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'style', 'templates', 'Templates', action='style_templates',
        contents=lambda h: _get_style_tab(h, _get_assets_templates),
        placement=4000)
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'style', 'contrib', 'Extensions', action='style_contrib',
        contents=lambda h: _get_style_tab(h, _get_assets_contrib),
        placement=5000)

