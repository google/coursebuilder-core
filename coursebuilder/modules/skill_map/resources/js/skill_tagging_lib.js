/**
 * This file contains the classes to manage Skill Mapping widgets.
 */

var SKILL_API_VERSION = '1';
var ESC_KEY = 27;

/*********************** Start Dependencies ***********************************/
// The following symols are required to be defined in the global scope:
//   cbShowMsg, cbShowMsgAutoHide
var showMsg = cbShowMsg;
var showMsgAutoHide = cbShowMsgAutoHide;
var hideMsg = cbHideMsg;
/************************ End Dependencies ************************************/

function parseAjaxResponse(s) {
  // XSSI prefix. Must be kept in sync with models/transforms.py.
  var xssiPrefix = ")]}'";
  return JSON.parse(s.replace(xssiPrefix, ''));
}

/**
 * A skills table builder.
 *
 * @class
 */
function SkillTable(skills, lessons) {
  // TODO(broussev): Add jasmine tests.
  this._skills = skills;
  this._lessons = lessons;
}

SkillTable.prototype = {
  _buildRow: function(skill) {
    var tr = $(
      '<tr class="row">' +
      '  <td><i class="diagnosis material-icons gcb-list__icon"></i></td>' +
      '  <td><a class="delete-skill">' +
      '    <i class="material-icons gcb-list__icon gcb-list__icon--rowhover">' +
      '      delete</i></a>' +
      '  </td> ' +
      '  <td class="skill-name"><a class="edit-skill">' + skill.name +
      '  </a></td>' +
      '</tr>');

    // add skill name
    tr.find('.diagnosis, a').data('id', skill.id);

    var diagnosis = this._skills.diagnosis(skill.id);
    if (diagnosis.status == SkillList.WARNING) {
      tr.find('.diagnosis').addClass('warning');
    } else if (diagnosis.status == SkillList.ERROR) {
      tr.find('.diagnosis').addClass('error');
    }

    // add skill description
    var td = $(
        '<td class="description">' +
          '<span class="skill-description"></span>' +
        '</td>'
    );
    td.find('.skill-description').text(skill.description);
    tr.append(td);

    // add skill prerequisites
    var td = $('<td></td>');
    var ol = $('<ol class="skill-display-root"></ol>');
    this._skills.eachPrerequisite(skill, function(prereq) {
      var prereqLi = $('<li class="skill"></li>').text(prereq.name);
      ol.append(prereqLi);
    });
    td.append(ol);
    tr.append(td);

    // add skill successors
    var td = $('<td></td>');
    var ol = $('<ol class="skill-display-root"></ol>');
    this._skills.eachSuccessor(skill, function(successor) {
      var successorLi = $('<li class="skill"></li>').text(successor.name);
      ol.append(successorLi);
    });
    td.append(ol);
    tr.append(td);

    // add skill lessons
    var td = $('<td></td>');
    var ol = $('<ol class="comma-list"></ol>');
    for (var i = 0; i < skill.lessons.length; i++) {
      var loc = skill.lessons[i];
      var a = $('<a class="skill-location"></a>')
          .text(loc.label)
          .attr('href', loc.href)
          .attr('title', loc.description);
      ol.append($('<li></li>').append(a));
    }
    td.append(ol);
    tr.append(td);

    return tr;
  },

  _skillsCount: function() {
    var that = this;
    return Object.keys(that._skills._skillLookupByIdTable).length;
  },

  _buildHeader: function() {
    var that = this;
    var thead = $(
      '<thead>' +
      '  <tr>' +
      '    <th class="gcb-list__cell--icon"></th>' +
      '    <th class="gcb-list__cell--icon"></th>' +
      '    <th class="skill">Skill <span class="skill-count"></span></th>' +
      '    <th class="description">Description</th>' +
      '    <th class="related-skills">Prerequisites</th>' +
      '    <th class="related-skills">Leads to</th>' +
      '    <th class="lessons">Lessons</th>' +
      '  </tr>' +
      '</thead>'
    );
    thead.find('.skill-count').text('(' + that._skillsCount() + ')');
    return thead;
  },

  _buildBody: function() {
    var that = this;
    var tbody = $('<tbody></tbody>');

    var i = 0;
    that._skills.eachSkill(function(skill) {
      var row = that._buildRow(skill);
      tbody.append(row);
    });

    function _onAjaxDeleteCallback(status, message) {
      if (status == 'success') {
        that._refresh();
        showMsg(message);
      } else {
        showMsg('Can\'t delete skill.');
      }
    }

    tbody.tooltip({
      items: '.diagnosis',
      content: function() {
        var skillId = $(this).data('id');
        var diagnosis = that._skills.diagnosis(skillId);
        var skill = that._skills.getSkillById(skillId);
        return that._diagnosisReport(skill, diagnosis);
      }
    });

    tbody.find('.delete-skill').on('click', function(e) {
      if (! confirm('Are you sure you want to delete the skill?')) {
        return false;
      }
      var skillId = $(this).data('id');
      that._skills.deleteSkill(_onAjaxDeleteCallback, skillId);
    });

    tbody.find('.edit-skill').on('click', function(e){
      var skillId = $(this).data('id');
      var skillPopUp = new EditSkillPopup(that._skills, that._lessons,
          skillId);
      skillPopUp.open(function() {
        that._refresh();
      });
    });

    return tbody;
  },

  _refresh: function() {
    this._table.find('thead').remove();
    this._table.append(this._buildHeader());
    this._table.find('tbody').remove();
    this._table.append(this._buildBody());
  },

  buildTable: function() {
    var that = this;

    this._content = $(
      '<div class="controls gcb-toggle-button-bar gcb-button-toolbar">' +
      '  <button class="material-icons gcb-toggle-button selected" disabled>' +
      '     view_list</button>' +
      '  <button class="material-icons gcb-toggle-button graph-view clickable' +
      '     " title="Show Skills graph">insert_chart</button>' +
      '  <button class="material-icons gcb-toggle-button add-new-skill"' +
      '     title="Add skill">add_box</button>' +
      '</div>' +
      '<div class="gcb-list gcb-list--autostripe">' +
      '  <table class="skill-map-table"></table>' +
      '</div>');

    this._table = this._content.find('.skill-map-table');
    this._table.append(that._buildHeader());

    this._content.find('.graph-view').on("click", function() {
      window.location.href = 'modules/skill_map?action=edit_dependency_graph';
    });

    this._content.find('.add-new-skill').on("click", function() {
      var skillPopUp = new EditSkillPopup(that._skills, that._lessons);
      skillPopUp.open(function() {
        that._refresh();
      });
    });

    this._refresh();

    return this._content;
  },

  _diagnosisReport: function(skill, diagnosis) {
    var that = this;
    if (diagnosis.status == SkillList.HEALTHY) {
      return null;
    }
    var panel = $(
        '<div class="skill-map-diagnosis-report">' +
        '  <div>' +
        '    The skill "<span class="skill-name"></span>":' +
        '  </div>' +
        '  <div class="diagnosis singleton">' +
        '    Does not lead to or from any other skills.' +
        '  </div>' +
        '  <div class="diagnosis cycles">' +
        '    Is part of a circular dependency:' +
        '    <ul class="elem-list"></ul>' +
        '  </div>' +
        '  <div` class="diagnosis long-chains">' +
        '    Is part of a long chain of dependencies:' +
        '    <ul class="elem-list"></ul>' +
        '  </div>' +
        '</div>');

    panel.find('.diagnosis').addClass('hidden');

    panel.find('.skill-name').text(skill.name);

    if (diagnosis.singleton) {
      panel.find('.singleton').removeClass('hidden');
    }

    if (diagnosis.cycles.length > 0) {
      panel.find('.diagnosis.cycles').removeClass('hidden');
      $.each(diagnosis.cycles, function(i, cycle) {
        // Each cycle goes in an li
        var li = $('<li></li>');
        $.each(cycle, function(j, cycleSkillId) {
          // Put all the elements of the cycle one after the other (CSS will)
          // interpolate a '-->' between entries
          var cycleSkill = that._skills.getSkillById(cycleSkillId);
          li.append($('<span class="elem"></span>').text(cycleSkill.name));
        });
        // Put the first element of the cycle at the end of the cycle too
        var firstSkill = that._skills.getSkillById(cycle[0]);
        li.append($('<span class="elem"></span>').text(firstSkill.name));
        panel.find('.diagnosis.cycles .elem-list').append(li);
      });
    }

    if (diagnosis.long_chains.length > 0) {
      panel.find('.diagnosis.long-chains').removeClass('hidden');
      $.each(diagnosis.long_chains, function(i, chain) {
        // Each chain goes in an li
        var li = $('<li></li>');
        $.each(chain, function(j, chainSkillId) {
          // Put all the elements of the chain one after the other (CSS will)
          // interpolate a '-->' between entries
          var chainSkill = that._skills.getSkillById(chainSkillId);
          li.append($('<span class="elem"></span>').text(chainSkill.name));
        });
        panel.find('.diagnosis.long-chains .elem-list').append(li);
      });
    }

    return panel;
  }
};

/**
 * A proxy to load and work with a list of skills from the server. Each of the
 * skills is an object with fields for "id", "name", and "description".
 *
 * @class
 */
function SkillList() {
  this._skillLookupByIdTable = {};
  this._diagnosisData = null;
  this._xsrfToken = null;
}
/**
 * Values for the graph diagnostics status.
 */
SkillList.HEALTHY = 1;
SkillList.WARNING = 2;
SkillList.ERROR = 3;


SkillList.prototype = {
  /**
   * Load the skill list from the server.
   *
   * @method
   * @param callback {function} A zero-args callback which is called when the
   *     skill list has been loaded.
   */
  load: function(callback) {
    var that = this;
    $.ajax({
      type: 'GET',
      url: 'rest/modules/skill_map/skill',
      dataType: 'text',
      success: function(data) {
        that._onLoad(callback, data);
      },
      error: function() {
        showMsg('Can\'t load the skills map.');
      }
    });
  },

  deleteSkill: function(callback, skillId) {
    var that = this;
    var skill = that.getSkillById(skillId);
    if (! skill) {
      return false;
    }
    var params = {
      'xsrf_token': that._xsrfToken,
      'key': skillId
    };
    var query_string = $.param(params);
    var url = 'rest/modules/skill_map/skill?' + query_string;
    $.ajax({
      url: url,
      type: 'DELETE',
      dataType: 'text',
      success: function (data) {
        that._onDeleteSkill(callback, data);
      },
      error: function () {
        callback('error');
      }
    });
    return true;
  },

  _onDeleteSkill: function(callback, data) {
    data = parseAjaxResponse(data);
    if (data.status != 200) {
      showMsg(data.message);
      return;
    }
    var payload = JSON.parse(data['payload']);
    this._updateFromPayload(payload);
    callback('success', data.message);
  },

  /**
   * @param id {string}
   * @return {object} The skill with given id, or null if no match.
   */
  getSkillById: function(id) {
    return this._skillLookupByIdTable[id];
  },

  /**
   * Iterate over the skills in the list.
   *
   * @param callback {function} A function taking a skill as its arg.
   */
  eachSkill: function(callback) {
    for (var prop in this._skillLookupByIdTable) {
      if (this._skillLookupByIdTable.hasOwnProperty(prop)) {
        callback(this._skillLookupByIdTable[prop]);
      }
    }
  },

  /**
   * Iterate over the prerequisites of a skill
   *
   * @param callback {function} A function taking a skill as its arg.
   */
  eachPrerequisite: function(skill, callback) {
    for (var i = 0; i < skill.prerequisite_ids.length; i++) {
      var prereq = this._skillLookupByIdTable[skill.prerequisite_ids[i]];
      if (prereq) {
        callback(prereq);
      }
    }
  },

  /**
   * Iterate over the successors of a skill
   *
   * @param callback {function} A function taking a skill as its arg.
   */
  eachSuccessor: function(skill, callback) {
    for (var i = 0; i < skill.successor_ids.length; i++) {
      var successor = this._skillLookupByIdTable[skill.successor_ids[i]];
      if (successor) {
        callback(successor);
      }
    }
  },

  /**
   * Create a new skill and store it on the server.
   *
   * @param callback {function} A callback which takes (skill, message) args
   * @param name {string}
   * @param description {string}
   * @param prerequisiteIds {array}
   * @param skillId
   */
  createOrUpdateSkill: function(callback, name, description, prerequisiteIds,
      lessonKeys, questionKeys, skillId) {

    var that = this;
    prerequisiteIds = prerequisiteIds || [];
    lessonKeys = lessonKeys || [];
    questionKeys = questionKeys || [];

    if (! name) {
      showMsg('Name can\'t be empty');
      $('.form-row .skill-name').addClass('invalid');
      return;
    }

    var prerequisites = [];
    for (var i = 0; i < prerequisiteIds.length; i++) {
      prerequisites.push({'id': prerequisiteIds[i]});
    }

    var lessons = [];
    for (var i = 0; i < lessonKeys.length; i++) {
      lessons.push({'key': lessonKeys[i]});
    }

    var questions = [];
    for (var i = 0; i < questionKeys.length; i++) {
      questions.push({'key': questionKeys[i]});
    }

    var requestDict = {
      xsrf_token: this._xsrfToken,
      payload: JSON.stringify({
        'version': SKILL_API_VERSION,
        'name': name,
        'description': description,
        'prerequisites': prerequisites,
        'lessons': lessons,
        'questions': questions
      })
    };
    if (skillId) {
      requestDict['key'] = skillId;
    }

    this._clearErrors();

    var request = JSON.stringify(requestDict);
    $.ajax({
      type: 'PUT',
      url: 'rest/modules/skill_map/skill',
      data: {'request': request},
      dataType: 'text',
      success: function(data) {
        that._onCreateOrUpdateSkill(callback, data);
      }
    });
  },

  _clearErrors: function() {
    $('.form-row .invalid').removeClass('invalid');
    hideMsg();
  },

  /**
   * @method
   * @param skillId {Number} The id of the skill to be diagnosed.
   * @return {object} with the following structure:
   *     {
   *       status {Number}: one of HEALTHY, WARNING, ERROR
   *       cycles: list of lists of cycles containing the skill
   *       long_chains: list of list of long chains containing the skill,
   *       singleton: boolean
   *     }
   */
  diagnosis: function(skillId) {
    var retval = {
      status: SkillList.HEALTHY,
      cycles: [],
      long_chains: [],
      singleton: false
    };

    var error = false;
    var warning = false;

    $.each(this._diagnosisData.cycles, function() {
      if (this.indexOf(skillId) >= 0) {
        error = true;
        retval.cycles.push(this);
      }
    });

    $.each(this._diagnosisData.long_chains, function() {
      if (this.indexOf(skillId) >= 0) {
        warning = true;
        retval.long_chains.push(this);
      }
    });

    if (this._diagnosisData.singletons.indexOf(skillId) >= 0) {
      warning = true;
      retval.singleton = true;
    }

    if (error) {
      retval.status = SkillList.ERROR;
    } else if (warning) {
      retval.status = SkillList.WARNING;
    }

    return retval;
  },

  _onLoad: function(callback, data) {
    data = parseAjaxResponse(data);
    if (data.status != 200) {
      showMsg('Unable to load skill map. Reload page and try again.');
      return;
    }
    this._xsrfToken = data['xsrf_token'];
    var payload = JSON.parse(data['payload']);
    this._updateFromPayload(payload);

    if (callback) {
      callback();
    }
  },

  _updateFromPayload: function(payload) {
    var that = this;
    var skills = payload['skills'];

    this._skillLookupByIdTable = [];
    $.each(skills, function() {
      that._skillLookupByIdTable[this.id] = this;
    });

    this._diagnosisData = payload['diagnosis'];
  },

  _onCreateOrUpdateSkill: function(callback, data) {
    data = parseAjaxResponse(data);
    if (data.status != 200) {
      showMsg(data.message);
      if (data.payload) {
        var payload = JSON.parse(data.payload);
        if (payload.messages) {
          $.each(payload.messages, function(key, val) {
            $('.form-row .' + key).addClass('invalid')
          })
        }
      }
      return;
    }
    var payload = JSON.parse(data.payload);
    this._updateFromPayload(payload);

    if (callback) {
      callback(payload.skill, data.message, data.status == 200);
    }
  }
};

function LocationList() {
  this._lessons = null;
  this._lessonsByKey = null;
  this._questions = null;
  this._questionsByKey = null;
}

LocationList.prototype = {
  load: function(callback) {
    var that = this;
    $.ajax({
      type: 'GET',
      url: 'rest/modules/skill_map/locations',
      dataType: 'text',
      success: function(data) {
        that._onLoad(callback, data);
      },
      error: function() {
        showMsg('Can\'t load the lesson map.');
      }
    });
  },

  eachLesson: function(callback) {
    $.each(this._lessons, function() {
      callback(this);
    });
  },

  getLessonByKey: function(key) {
    return this._lessonsByKey[key];
  },

  eachQuestion: function(callback) {
    $.each(this._questions, function() {
      callback(this);
    });
  },

  getQuestionByKey: function(key) {
    return this._questionsByKey[key];
  },

  _onLoad: function(callback, data) {
    var that = this;
    data = parseAjaxResponse(data);
    if (data.status != 200) {
      showMsg('Unable to load location data. Reload page and try again.');
      return;
    }
    var payload = JSON.parse(data['payload']);

    this._lessons = payload['lessons'];
    this._lessonsByKey = [];
    $.each(this._lessons, function() {
      that._lessonsByKey[this.key] = this;
    });

    this._questions = payload['questions'];
    this._questionsByKey = [];
    $.each(this._questions, function() {
      that._questionsByKey[this.key] = this;
    });

    if (callback) {
      callback();
    }
  }
};

/**
 * A modal popup to edit or add skills.
 *
 * @class
 * @param skillList {SkillList}
 * @param locationList {LocationList} If the locationList is null, then the
 *     editor will not offer location tagging of the skill.
 * @param skillId {string} If the skillId is null, the editor will be configured
 *     to create a new skill rather that edit an existing one.
 */
function EditSkillPopup(skillList, locationList, skillId) {
  var that = this;
  this._skillId = skillId;
  this._skillList = skillList;
  this._locations = locationList;
  this._prerequisiteIds = [];
  this._skillList.eachSkill(function(skill) {
    if ($.inArray(that._skillId, skill.successor_ids) >= 0) {
      that._prerequisiteIds.push(skill.id);
    }
  });

  this._documentBody = $(document.body);
  this._lightbox = new window.gcb.Lightbox();
  this._form = $(
      '<div class="edit-skill-popup">' +
      '  <h2 class="title"></h2>' +
      '  <div class="form-row">' +
      '    <label class="required-label">Skill</label>' +
      '    <input type="text" class="skill-name"' +
      '        placeholder="e.g. Structure Tables">' +
      '  </div>' +
      '  <div class="form-row">' +
      '    <label>Description</label>' +
      '    <textarea class="skill-description"' +
      '        placeholder="e.g. Structure data into tables"></textarea>' +
      '  </div>' +
      '  <div class="form-row">' +
      '    <label class="strong skill-prerequisites">Prerequisites</label>' +
      '    <div class="prerequisites"></div>' +
      '  </div>' +
      '  <div class="form-row lesson-row">' +
      '    <label class="strong skill-lessons">Lessons</label>' +
      '    <div class="lessons"></div>' +
      '  </div>' +
      '  <div class="form-row question-row">' +
      '    <label class="strong skill-questions">Questions</label>' +
      '    <div class="questions"></div>' +
      '  </div>' +
      '  <div class="controls">' +
      '    <button class="gcb-button new-skill-save-button">Save</button>' +
      '    <button class="gcb-button new-skill-cancel-button">Cancel</button>' +
      '  </div>' +
      '</div>');

  this._nameInput = this._form.find('.skill-name');
  this._descriptionInput = this._form.find('.skill-description');

  this._initPrereqDisplay();

  if (locationList) {
    this._initLessonDisplay();
    this._initQuestionDisplay();
  } else {
    this._form.find('.lesson-row').hide();
    this._form.find('.question-row').hide();
  }

  if (skillId !== null && skillId !== undefined) {
    var skill = this._skillList.getSkillById(skillId);
    var title = 'Edit Skill';
    this._nameInput.val(skill.name);
    this._descriptionInput.val(skill.description);
    this._skillList.eachPrerequisite(skill, function(prereq) {
      that._prereqDisplay.add(prereq.id, prereq.name);
    });
    $.each(skill.lessons, function() {
      that._lessonDisplay.add(this.key,
          this.label + ' ' + this.description);
    });
    $.each(skill.questions, function() {
      that._questionDisplay.add(
          this.key, this.description);
    });
  } else {
    var title = 'Create New Skill';
  }

  this._form.find('h2.title').text(title);

  this._form.find('button.new-skill-save-button').click(function() {
    that._onSave();
    return false;
  });

  this._form.find('button.new-skill-cancel-button')
    .click(function() {
      that._onCancel();
      return false;
    }
  );
}

EditSkillPopup.prototype = {
  /**
   * Display the popup to the user.
   *
   * @param callback {function} Called with the new skill after a skill is
   *     added. The skill is automatically added to the SkillList, so there is
   *     no need to update the SkillList in the callback.
   */
  open: function(callback) {
    this._onAjaxCreateSkillCallback = callback;
    this._lightbox
      .bindTo(this._documentBody)
      .setContent(this._form)
      .show();
    $('.skill-name').focus();

    var that = this;
    $(document).on('keydown', function(e) {
      if (e.which == ESC_KEY) {
        that._lightbox.close();
        $(document).unbind('keydown');
      }
    });

    return this;
  },

  _resetPrereqSelector: function() {
    var that = this;
    this._prereqSelector.clear();
    this._skillList.eachSkill(function(skill) {
      if (that._skillId != skill.id &&
          $.inArray(skill.id, that._prerequisiteIds) == -1) {
        that._prereqSelector.add(skill.id, skill.name);
      }
    });
  },

  _initPrereqDisplay: function() {
    // Set up a display and a chooser for the prerequisites and bind them
    // together
    var that = this;
    this._prereqDisplay = new ListDisplay(
      'skill-display-root', 'skill', function(sid) {
        that._prerequisiteIds = $.grep(that._prerequisiteIds, function(val) {
          return val != sid;
        });
        that._resetPrereqSelector();
      }
    );
    this._prereqSelector = new ItemSelector(function(selectedSkillIds) {
      $.each(selectedSkillIds, function() {
        var skill = that._skillList.getSkillById(this);
        that._prereqDisplay.add(skill.id, skill.name);
        that._prerequisiteIds.push(skill.id);
      });
      that._resetPrereqSelector();
    }, '+ Add Skill');
    this._resetPrereqSelector();

    this._form.find('.prerequisites')
        .append(this._prereqDisplay.element())
        .append(this._prereqSelector.element());
  },

  _initLessonDisplay: function() {
    // Set up display and chooser for tagging lessons and bind them together
    var that = this;
    this._lessonDisplay = new ListDisplay(
        'location-display-root', 'location');
    this._lessonSelector = new ItemSelector(function(selectedLessonIds) {
      $.each(selectedLessonIds, function() {
        var lesson = that._locations.getLessonByKey(this);
        that._lessonDisplay.add(this, lesson.label + ' ' + lesson.description);
      });
    }, '+ Add Lesson', 'Lesson...');
    this._locations.eachLesson(function(lesson) {
      that._lessonSelector.add(lesson.key,
          lesson.label + ' ' + lesson.description);
    });

    this._form.find('.lessons')
        .append(this._lessonDisplay.element())
        .append(this._lessonSelector.element());
  },

  _initQuestionDisplay: function() {
    // Set up a display and a chooser for tagging questions and bind them
    // together
    var that = this;
    this._questionDisplay = new ListDisplay('question-display-root',
        'question');
    this._questionSelector = new ItemSelector(function(selectedQuestionIds) {
      $.each(selectedQuestionIds, function() {
        var question = that._locations.getQuestionByKey(this);
        that._questionDisplay.add(this, question.description);
      });
    }, '+ Add Question', 'Question...');
    this._locations.eachQuestion(function(question) {
      that._questionSelector.add(question.key, question.description);
    });

    this._form.find('.questions')
        .append(this._questionDisplay.element())
        .append(this._questionSelector.element());
  },

  _onSave: function() {
    var that = this;
    var name = this._nameInput.val();
    var description = this._descriptionInput.val();
    var prerequisiteIds = this._prerequisiteIds;
    var locationKeys = this._lessonDisplay ?
        this._lessonDisplay.items() : [];
    var questionIds = this._questionDisplay ?
        this._questionDisplay.items() : [];

    function onSkillCreatedOrUpdated(skill, message, closePopup) {
      showMsgAutoHide(message);
      that._onAjaxCreateSkillCallback(skill);
      if (closePopup) {
        that._lightbox.close()
      }
    }
    this._skillList.createOrUpdateSkill(onSkillCreatedOrUpdated,
        name, description, prerequisiteIds, locationKeys, questionIds,
        that._skillId);
  },

  _onCancel: function() {
    this._lightbox.close();
  }
};

/**
 * A container to display a list of items as labels with buttons for removal.
 *
 * @class
 * @param listClass {string} The CSS class for the container.
 * @param itemClass {string} The CSS class for each item in the list.
 * @param onRemoveCallback {function} Called with the id of an item whenever an
 *     item is removed from the view.
 */
function ListDisplay(listClass, itemClass, onRemoveCallback) {
  this._ol = $('<ol></ol>');
  this._ol.addClass(listClass);
  this._itemClass = itemClass;
  this._onRemoveCallback = onRemoveCallback;
  this._items = {};
}

ListDisplay.prototype = {
  /**
   * Remove all item from the view.
   *
   * @method
   */
  empty: function() {
    this._ol.empty();
    this._items = {};
  },

  /**
   * Add a new item to the view.
   *
   * @method
   * @param id {string} The item id, which is passed to the onRemoveCallback.
   * @param label {string} The labl of the item to be displayed in the list.
   */
  add: function(id, label) {
    var that = this;
    var li = $('<li></li>');
    var closeButton = $('<button class="close">x</button>');

    // Refuse to add an existing element
    if (this._items[id]) {
      return;
    }

    li.addClass(this._itemClass).text(label).append(closeButton);
    li.addClass('removable')

    closeButton.click(function() {
      li.remove();
      delete that._items[id];
      if (that._onRemoveCallback) {
        that._onRemoveCallback(id);
      }
      return false;
    });

    this._ol.append(li);
    this._items[id] = true;
  },

  /**
   * @return {Element} The root DOM element for the display.
   */
  element: function() {
    return this._ol[0];
  },

  /**
   * @return {Array} The list of item id's which are in the display.
   */
  items: function() {
    var that = this;
    return $.map(this._items, function(flag, id) {
      return that._items.hasOwnProperty(id) ? id : null;
    });
  }
};

/**
 * A class to display a widget for item selection.
 *
 * @class
 * @param onItemsSelectedCallback {function} Callback called with a list of
 *     item ids whenever a selection is performed.
 * @param addLabel {string} Optional label for ADD button.
 */
function ItemSelector(onItemsSelectedCallback, label, placeholder) {
  this._documentBody = $(document.body);
  this._onItemsSelectedCallback = onItemsSelectedCallback;

  label = label || '+ Add';
  placeholder = placeholder || 'Skill...';

  this._rootDiv = $(
    '<div class="item-selector-root">' +
    '  <button class="add"></button>' +
    '  <div class="selector">' +
    '    <div><input class="search" type="text"></div>' +
    '    <ol class="item-list"></ol>' +
    '    <div><button class="select action">OK</button></div>' +
    '  </div>' +
    '</div>');
  this._rootDiv.find('button.add').text(label);
  this._rootDiv.find('input.search').attr('placeholder', placeholder);

  this._addItemButton = this._rootDiv.find('button.add');
  this._addItemWidgetDiv = this._rootDiv.find('div.selector');
  this._searchTextInput = this._rootDiv.find('input.search');
  this._selectNewItemButton = this._rootDiv.find('button.select');
  this._selectItemListOl = this._rootDiv.find('ol.item-list');

  this._addItemButton.prop('disabled', true);
  this._selectNewItemButton.prop('disabled', true);

  this._bind();
  this._close();
}

ItemSelector.prototype = {
  /**
   * @method
   * @return {Element} The root DOM element for the selector.
   */
  element: function() {
    return this._rootDiv[0];
  },

  /**
   * Add an item to the selector.
   *
   * @method
   * @param id {string} the id of the item
   * @param name {string} the display name of the item
   */
  add: function(id, name) {
    var that = this;
    var itemLi = $('<li/>');
    var label = $('<label></label>');
    var checkbox = $('<input type="checkbox" class="item-select">');

    checkbox.change(function() {
      if (that._addItemWidgetDiv.find('input.item-select:checked').length) {
        that._selectNewItemButton.prop('disabled', false);
      } else {
        that._selectNewItemButton.prop('disabled', true);
      }
    });

    checkbox.data('id', id);

    label.append(checkbox);
    label.append($('<span></span>').text(name));

    itemLi.append(label);
    this._selectItemListOl.append(itemLi);

    this._addItemButton.prop('disabled', false);
  },

  clear: function() {
    this._selectItemListOl.empty();
    this._addItemButton.prop('disabled', true);
  },

  _bind: function() {
    var that = this;

    this._addItemButton.click(function() {
      that._addItemWidgetDiv.show();
      that._positionAddItemWidgetDiv();
      return false;
    });

    this._documentBody.click(function(evt) {
      if ($(evt.target).closest('div.selector').length == 0) {
        that._close();
      }
    });

    this._searchTextInput.keyup(function(evt) {
      that._filterAddItemWidget(that._searchTextInput.val());
    });

    this._selectNewItemButton.click(function() {
      that._selectItems();
      that._close();
      return false;
    });
  },

  /**
   * Choose an optimal position for the addItemWidgetDiv.
   */
  _positionAddItemWidgetDiv: function() {
    // PADDING = (margin used in CSS styling) - (extra padding)
    PADDING = 22 - 10;

    // Remove any previous styling
    this._addItemWidgetDiv.css('top', null);

    var bounds = this._addItemWidgetDiv[0].getBoundingClientRect();
    var overflow = bounds.bottom - $(window).height();
    var top = PADDING - overflow;
    if (overflow > 0 && top + bounds.top >= 0) {
      this._addItemWidgetDiv.css('top', top);
    }
  },

  _close: function() {
    this._addItemWidgetDiv.hide();
    this._searchTextInput.val('');
    this._selectItemListOl.find('li').show();
    this._addItemWidgetDiv.find('input.item-select').prop('checked', false);
    this._selectNewItemButton.prop('disabled', true);
  },

  _filterAddItemWidget: function(filter) {
    filter = filter.toLowerCase();
    this._selectItemListOl.find('> li').show();
    this._selectItemListOl.find('> li span').each(function() {
      if ($(this).text().toLowerCase().indexOf(filter) == -1) {
        $(this).closest('li').hide();
      }
    });
  },

  _selectItems: function() {
    var that = this;
    var selectedItems = this._addItemWidgetDiv
        .find('input.item-select:checked')
        .map(function() {
          return $(this).data('id');
        });
    this._onItemsSelectedCallback(selectedItems);
  }
}

function SkillEditorForOeditor(env) {
  var that = this;

  this._env = env;
  this._skillList = new SkillList();
  this._prerequisiteIds = [];

  this._prereqDisplay = new ListDisplay('skill-display-root', 'skill',
    function(skillId) {
      that._onRemoveCallback(skillId);
    }
  );
  this._prereqSelector = new ItemSelector(function(selectedSkillIds) {
    that._onSkillsSelectedCallback(selectedSkillIds);
  }, '+ Add Skill');

  var newSkillDiv = $('<div class="new-skill"></div>');
  var newSkillButton = $('<button class="add">+ Create New Skill</button>');
  newSkillButton.click(function() {
    new EditSkillPopup(that._skillList, null, null).open(function(skill) {
      that._onSkillsSelectedCallback([skill.id]);
      that._populatePrereqSelector();
    });
    return false;
  });
  newSkillDiv.append(newSkillButton);

  this._skillWidgetDiv = $('<div class="inputEx-Field skill-widget"></div>');
  this._skillWidgetDiv.append(this._prereqDisplay.element());

  var buttonDiv = $('<div class="skill-map-buttons"></div>');
  this._skillWidgetDiv.append(buttonDiv);
  buttonDiv.append(this._prereqSelector.element());
  buttonDiv.append(newSkillDiv);
}

SkillEditorForOeditor.prototype = {
  element: function() {
    return this._skillWidgetDiv;
  },
  init: function() {
    var that = this;
    this._skillList.load(function() {
      that._populateSkillList();
      that._populatePrereqSelector();
    });
  },

  _populatePrereqSelector: function() {
    var that = this;
    this._prereqSelector.clear();
    this._skillList.eachSkill(function(skill) {
      if ($.inArray(skill.id, that._prerequisiteIds) == -1) {
        that._prereqSelector.add(skill.id, skill.name);
      }
    });
  },

  _onSkillsSelectedCallback: function(selectedSkillIds) {
    // When new skills are selected in the SkillSelector, update the OEditor
    // form and repopulate the SkillDisplay.
    var that = this;
    $.each(selectedSkillIds, function() {
      if (! that._formContainsSkillId(this)) {
        that._env.form.inputsNames.skills.addElement({'skill': this});
        that._prerequisiteIds.push(parseInt(this));
      }
    });
    this._populateSkillList();
    this._populatePrereqSelector();
  },

  _onRemoveCallback: function (skillId) {
    // When a skill is removed from the SkillDisplay, also remove it from the
    // OEditor form.
    var that = this;
    $.each(this._env.form.inputsNames.skills.subFields, function(i) {
      var id = this.inputsNames.skill.getValue();
      if (id === skillId) {
        that._env.form.inputsNames.skills.removeElement(i);
        that._prerequisiteIds = $.grep(that._prerequisiteIds, function(val) {
          return val != skillId;
        });
        that._populatePrereqSelector();
        return false;
      }
    });
  },

  _populateSkillList: function() {
    // Populate the SkillDisplay with the skills in the OEditor form.
    var that = this;
    this._prereqDisplay.empty();
    $.each(this._env.form.inputsNames.skills.subFields, function() {
      var id = this.inputsNames.skill.getValue();
      var skill = that._skillList.getSkillById(id);
      if (skill) {
        that._prereqDisplay.add(skill.id, skill.name);
        that._prerequisiteIds.push(skill.id);
      }
    });
  },

  _formContainsSkillId: function(skillId) {
    var fields = this._env.form.inputsNames.skills.subFields;
    for(var i = 0; i < fields.length; i++) {
      var id = fields[i].inputsNames.skill.getValue();
      if (skillId.toString() === id.toString()) {
        return true;
      }
    }
    return false;
  }
};

/**
 * A skill selector data provider builder for analytics.
 *
 * @class
 */
function SkillSelectorForAnalytics(skillList, selectorTitle) {
  var that = this;
  this._skillList = skillList;
  var title = selectorTitle || 'Selected Skills';

  this._skillsDiv = $(
      '<div class="edit-skill-popup">' +
      '  <div class="form-row">' +
      '    <label class="strong"></label>' +
      '    <div class="skill-prerequisites"></div>' +
      '  </div>' +
      '</div>');
  this._skillsDiv.find('.form-row > label').text(title);
  this._initSelectedSkillsDisplay();
}

SkillSelectorForAnalytics.prototype = {
  _initSelectedSkillsDisplay: function() {
    // Set up a display and a chooser for skills.
    var that = this;

    this._selectedSkillsDisplay = new ListDisplay(
        'skill-display-root', 'skill',
        function(skillId) {
          that._onDropSkill(skillId);
        });

    this._skillsSelector = new ItemSelector(function(selectedSkillIds) {
      $.each(selectedSkillIds, function() {
        var skill = that._skillList.getSkillById(this);
        that._selectedSkillsDisplay.add(skill.id, skill.name);
      });
      var skillIds = that._selectedSkillsDisplay.items();
      if (skillIds.length > 0) {
        that._loadData(skillIds);
      }
    }, '+ Select Skill');

    this._skillList.eachSkill(function(skill) {
      that._skillsSelector.add(skill.id, skill.name);
    });

    this._skillsDiv.find('.skill-prerequisites')
        .append(this._selectedSkillsDisplay.element())
        .append(this._skillsSelector.element());
  },

  _deleteChart: function() {
    $('#advanced-div').empty();
    $('#selector-div').empty();
  },

  _onDropSkill: function(skillId) {
    if (this._selectedSkillsDisplay.items().length == 0) {
      this._deleteChart();
    }
    else {
      this._loadData(this._selectedSkillsDisplay.items());
    }
  },

  build: function(visualizationCallback) {
    this._visualizationCallback = visualizationCallback;
    return this._skillsDiv;
  },

  _loadData: function(skillIds) {
    var that = this;
    var encodedIds = $.param({ids: skillIds}, true);
    $.ajax({
      type: 'GET',
      url: 'rest/modules/skill_map/skill_aggregate_count?' + encodedIds,
      dataType: 'text',
      success: function(response) {
        that._onLoadData(skillIds, response);
      },
      error: function() {
        showMsg('Unable to load skill data. Reload page and try again.');
      }
    });
  },

  _onLoadData: function(requestedSkillIds, response) {
    response = parseAjaxResponse(response);
    if (response.status != 200) {
      showMsg('Unable to load skill data. Please reload page and try again.');
      return;
    }
    var payload = JSON.parse(response['payload']);
    var header = payload['column_headers'];
    var skillIds = header.slice(1, header.length).map(function(x){
      return parseInt(x);
    });
    var data = payload['data'];
    this._visualizationCallback(skillIds, data, requestedSkillIds);
  }
};

/**
 * Export the classes which will be used in global scope.
 */
window.LocationList = LocationList;
window.SkillEditorForOeditor = SkillEditorForOeditor;
window.SkillList = SkillList;
window.SkillTable = SkillTable;
window.SkillSelectorForAnalytics = SkillSelectorForAnalytics;
