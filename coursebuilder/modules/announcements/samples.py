# Copyright 2012 Google Inc. All Rights Reserved.
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

"""Sample announcements."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import datetime


SAMPLE_ANNOUNCEMENT_1 = {
    'edit_url': None,
    'title': 'Example Announcement',
    'date': datetime.date(2012, 10, 6),
    'is_draft': False,
    'html': """
        <br>Certificates will be e-mailed to qualifying participants by
        Friday, October 12.
        <br>
        <br>Do you want to check your assessment scores? Visit the
        <a href="student/home">"My profile"</a> page!</p>
        """}

SAMPLE_ANNOUNCEMENT_2 = {
    'edit_url': None,
    'title': 'Welcome to Class 6 and the Post-class Assessment',
    'date': datetime.date(2012, 10, 5),
    'is_draft': True,
    'html': """
        <br>Welcome to the final class! <a href="class?class=6"> Class 6</a>
        focuses on combining the skills you have learned throughout the class
        to maximize the effectiveness of your searches.
        <br>
        <br><b>Customize Your Experience</b>
        <br>You can customize your experience in several ways:
        <ul>
          <li>You can watch the videos multiple times for a deeper understanding
          of each lesson. </li>
          <li>You can read the text version for each lesson. Click the button
          above the video to access it.</li>
          <li>Lesson activities are designed for multiple levels of experience.
          The first question checks your recall of the material in the video;
          the second question lets you verify your mastery of the lesson; the
          third question is an opportunity to apply your skills and share your
          experiences in the class forums. You can answer some or all of the
          questions depending on your familiarity and interest in the topic.
          Activities are not graded and do not affect your final grade. </li>
          <li>We'll also post extra challenges in the forums for people who seek
          additional opportunities to practice and test their new skills!</li>
        </ul>

        <br><b>Forum</b>
        <br>Apply your skills, share with others, and connect with your peers
        and course staff in the <a href="forum">forum.</a> Discuss your favorite
        search tips and troubleshoot technical issues. We'll also post bonus
        videos and challenges there!

        <p> </p>
        <p>For an optimal learning experience, please plan to use the most
        recent version of your browser, as well as a desktop, laptop or a tablet
        computer instead of your mobile phone.</p>
        """}

SAMPLE_ANNOUNCEMENTS = [SAMPLE_ANNOUNCEMENT_1, SAMPLE_ANNOUNCEMENT_2]
