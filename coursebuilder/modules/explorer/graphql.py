# Copyright 2016 Google Inc. All Rights Reserved.
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

"""GraphQL schema extensions for the Course Explorer."""


import graphene
from models import courses
from modules.gql import gql
from modules.explorer import settings


class Link(graphene.ObjectType):
    name = graphene.String()
    url = graphene.String()


class Image(graphene.ObjectType):
    url = graphene.String()
    alt_text = graphene.String()


class PrivacyTerms(graphene.ObjectType):
    url = graphene.String()


class CourseExplorer(graphene.ObjectType):
    extra_content = graphene.String()


class Site(graphene.ObjectType):
    title = graphene.String()
    logo = graphene.Field(Image)
    institution = graphene.Field(Link)
    privacy_terms = graphene.Field(PrivacyTerms)
    course_explorer = graphene.Field(CourseExplorer)

    def __init__(self, data, **kwargs):
        super(Site, self).__init__(**kwargs)
        self.data = data

    def resolve_title(self, args, info):
        return self.data.get('title')

    def resolve_logo(self, args, info):
        try:
            return Image(
                alt_text=self.data.get('logo_alt_text', ''),
                url=settings.make_logo_url(
                    self.data['logo_mime_type'],
                    self.data['logo_bytes_base64']),
                )
        except KeyError:
            return None

    def resolve_institution(self, args, info):
        return Link(
            name=self.data.get('institution_name'),
            url=self.data.get('institution_url'))

    def resolve_privacy_terms(self, args, info):
        return PrivacyTerms(url=self.data.get('privacy_terms_url'))

    def resolve_course_explorer(self, args, info):
        return CourseExplorer(extra_content=self.data.get('extra_content'))


class CourseCategory(graphene.ObjectType):
    name = graphene.String()


def resolve_site(gql_root, args, info):
    try:
        return Site(settings.get_course_explorer_settings_data())
    except ValueError:
        return Site({})


def resolve_estimated_workload(gql_course, args, info):
    return courses.Course.get_named_course_setting_from_environ(
        'estimated_workload', gql_course.course_environ)


def resolve_category(gql_course, args, info):
    name = courses.Course.get_named_course_setting_from_environ(
        'category_name', gql_course.course_environ)
    return None if name is None else CourseCategory(name=name)


def register():
    gql.Query.add_to_class(
        'site', graphene.Field(Site, resolver=resolve_site))

    gql.Course.add_to_class(
        'estimated_workload', graphene.String(
            resolver=resolve_estimated_workload))
    gql.Course.add_to_class(
        'category', graphene.Field(CourseCategory, resolver=resolve_category))
