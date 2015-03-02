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
/************************ End Dependencies ************************************/

function parseAjaxResponse(s) {
  // XSSI prefix. Must be kept in sync with models/transforms.py.
  var xssiPrefix = ")]}'";
  return JSON.parse(s.replace(xssiPrefix, ''));
}

/**
 * InputEx adds a JSON prettifier to Array and Object. This works fine for
 * InputEx code but breaks some library code (e.g., jQuery.ajax). Use this
 * to wrap a function which should be called with the InputEx extras turned
 * off.
 *
 * @param f {function} A zero-args function executed with prettifier removed.
 */
function withInputExFunctionsRemoved(f) {
  var oldArrayToPrettyJsonString = Array.prototype.toPrettyJSONString;
  var oldObjectToPrettyJsonString = Object.prototype.toPrettyJSONString;
  delete Array.prototype.toPrettyJSONString;
  delete Object.prototype.toPrettyJSONString;

  try {
    f();
  } finally {
    Array.prototype.toPrettyJSONString = oldArrayToPrettyJsonString;
    Object.prototype.toPrettyJSONString = oldObjectToPrettyJsonString;
  }
}

/**
 * A skills table builder.
 *
 * @class
 */
function SkillTable(skillList) {
  // TODO(broussev): Add jasmine tests.
  this._skillList = skillList;
}

SkillTable.prototype = {
  _buildRow: function(skill) {
    var tr = $('<tr class="row"></tr>');

    // add skill name
    var td = $(
        '<td>' +
        '  <span class="skill-name"></span> ' +
        '  <button class="edit-skill">Edit</button> ' +
        '  <button class="delete-skill">Delete</button> ' +
        '</td>'
    );
    td.find('.edit-skill, .delete-skill').data('id', skill.id);
    td.find('.skill-name').text(skill.name);
    tr.append(td);

    // add skill description
    var td = $(
        '<td>' +
          '<span class="skill-description"></span>' +
        '</td>'
    );
    td.find('.skill-description').text(skill.description);
    tr.append(td);

    // add skill prerequisites
    var td = $('<td></td>');
    for (var i = 0; i < skill.prerequisites.length; i++) {
      var span = $('<span class="prerequisite"></span>')
          .text(skill.prerequisites[i].name);
      td.append(span);
    }
    tr.append(td);

    // add skill locations
    var td = $('<td></td>');
    for (var i = 0; i < skill.locations.length; i++) {
      var loc = skill.locations[i]
      var title = loc.unit.title + ' ' + loc.lesson.title;
      var a = $('<a class="skill-location"></a>')
          .text(loc.label)
          .attr('href', loc.href)
          .attr('title', title);
      td.append(a);
    }
    tr.append(td);

    return tr;
  },

  _skillsCount: function() {
    var that = this;
    return Object.keys(that._skillList._skillLookupByIdTable).length;
  },

  _buildHeader: function() {
    var that = this;
    var thead = $(
      '<thead><tr><th width="15%">Skill ' +
      '<span class="skill-count"></span></th>' +
      '<th width="35%">Description</th>' +
      '<th width="45%">Prerequisites</th>' +
      '<th width="5%">Lessons</th>' +
      '</tr></thead>'
    );
    thead.find('.skill-count').text('(' + that._skillsCount() + ')')
    return thead;
  },

  buildTable: function() {
    var that = this;
    var i = 0;

    var table = $('<table class="skill-map-table"></table>');
    table.append(that._buildHeader());
    var tbody = $('<tbody></tbody>');
    tbody.append($(
      '<tr><td colspan="4">' +
      '<button class="add-new-skill">+ Add Skill</button>' +
      '</td></tr>'));

    function onAjaxAddSkillCallback(skills) {
      that._skillList._skillLookupByIdTable = {};
      $.each(skills, function() {
        that._skillList._skillLookupByIdTable[this.id] = this;
      });
      $('.skill-map-table').replaceWith(that.buildTable());
    }

    var addSkillButton = tbody.find('.add-new-skill');
    addSkillButton.on("click", function(e) {
      skillPopUp = new SkillsTableSkillPopup(that._skillList, 'new', null);
      skillPopUp.open(onAjaxAddSkillCallback);
    });

    that._skillList.eachSkill(function(skill) {
      var row = that._buildRow(skill);
      row.addClass( i % 2 == 0 ? 'even' : 'odd');
      tbody.append(row);
    });

    function _onAjaxDeleteCallback(status, message) {
      if (status == 'success') {
        $('.skill-map-table').replaceWith(that.buildTable());
        showMsg(message);
      } else {
        showMsg('Can\'t delete skill.');
      }
    }

    tbody.find('.delete-skill').on('click', function(e) {
      if (! confirm('Are you sure you want to delete the skill?')) {
        return false;
      }
      var skillId = $(this).data('id');
      that._skillList.deleteSkill(_onAjaxDeleteCallback, skillId);
    });

    function onAjaxEditSkillCallback(skills) {
      that._skillList._skillLookupByIdTable = {};
      $.each(skills, function() {
        that._skillList._skillLookupByIdTable[this.id] = this;
      });
      $('.skill-map-table').replaceWith(that.buildTable());
    }

    tbody.find('.edit-skill').on('click', function(e){
      var skillId = $(this).data('id');
      skillPopUp = new SkillsTableSkillPopup(that._skillList, 'edit', skillId);
      skillPopUp.open(onAjaxEditSkillCallback);
    });

    table.append(tbody);
    return table;
  }
};

/**
 * A proxy to load and work with a list of skills from the server. Each of the
 * skills is an object with fields for "id", "name", and "description".
 *
 * @class
 */
function SkillList() {
  // TODO(broussev): Add jasmine tests.
  this._skillLookupByIdTable = {};
  this._onLoadCallback = null;
  this._xsrfToken = null;
}

SkillList.prototype = {
  /**
   * Load the skill list from the server.
   *
   * @method
   * @param callback {function} A zero-args callback which is called when the
   *     skill list has been loaded.
   */
  load: function(callback, loadSkillInfos) {
    var that = this;
    this._onLoadCallback = callback;
    var handler = (loadSkillInfos) ? 'skill' : 'skill_list';
    $.ajax({
      type: 'GET',
      url: 'rest/modules/skill_map/' + handler,
      dataType: 'text',
      success: function(data) {
        that._onLoad(data);
      },
      error: function() {
        showMsg('Can\'t load the skills map.');
      }
    });
  },

  deleteSkill: function(callback, skillId) {
    var that = this;
    var skill = that.getSkillById(skillId);
    if (!skill) {
      return false;
    }
    var params = {
      'xsrf_token': that._xsrfToken,
      'key': skillId
    };
    var query_string = $.param(params);
    var url = 'rest/modules/skill_map/skill?' + query_string;
    withInputExFunctionsRemoved(function() {
      $.ajax({
        url: url,
        type: 'DELETE',
        dataType: 'text',
        success: function (data) {
          data = parseAjaxResponse(data);
          if (data.status == 200) {
            that._delete(skillId);
            callback('success', data.message);
          }
        },
        error: function () {
          callback('error');
        }
      });
    });
  },

  _delete: function(skillId) {
    delete this._skillLookupByIdTable[skillId];
    this.eachSkill(function(skill) {
      for (var i = 0; i < skill.prerequisites.length; i++) {
        if (skill.prerequisites[i].id == skillId) {
          skill.prerequisites.splice(i, 1);
        }
      }
    });
    return;
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
   * Create a new skill and store it on the server.
   *
   * @param callback {function} A callback which takes (skill, message) args
   * @param name {string}
   * @param description {string}
   * @param prerequisiteIds {array}
   * @param skillId
   */
  createOrUpdateSkill: function(callback, name, description, prerequisiteIds,
                                skillId) {
    var that = this;
    prerequisiteIds = prerequisiteIds || [];

    if (! name) {
      showMsg('Name can\'t be empty');
      return;
    }

    prerequisites = [];
    for (var i = 0; i < prerequisiteIds.length; i++) {
      prerequisites.push({'id': prerequisiteIds[i]});
    }

    var requestDict = {
      xsrf_token: this._xsrfToken,
      payload: JSON.stringify({
        'version': SKILL_API_VERSION,
        'name': name,
        'description': description,
        'prerequisites': prerequisites
      })
    };
    if (skillId) {
      requestDict['key'] = skillId;
    }

    var request = JSON.stringify(requestDict);

    withInputExFunctionsRemoved(function() {
      $.ajax({
        type: 'PUT',
        url: 'rest/modules/skill_map/skill',
        data: {'request': request},
        dataType: 'text',
        success: function(data) {
          that._onAjaxCreateOrUpdateSkill(callback, data, name,
              description, prerequisiteIds);
        }
      });
    });
  },

  _onLoad: function(data) {
    var that = this;
    data = parseAjaxResponse(data);
    if (data['status'] != 200) {
      showMsg('Unable to load skill map. Reload page and try again.');
      return;
    }
    this._xsrfToken = data['xsrf_token'];
    var payload = JSON.parse(data['payload']);
    var skillList = payload['skill_list'];

    $.each(skillList, function() {
      that._skillLookupByIdTable[this.id] = this;
    });

    if (this._onLoadCallback) {
      this._onLoadCallback();
    }
  },

  _onAjaxCreateOrUpdateSkill: function(callback, data, name, description,
                                       prerequisiteIds) {
    data = parseAjaxResponse(data);
    if  (data.status != 200) {
      showMsg(data.message);
      return;
    }
    var payload = JSON.parse(data.payload);
    var skill = {
      'id': payload.skill.id,
      'name': payload.skill.name,
      'description': payload.skill.description,
      'prerequisite_ids': payload.skill.prerequisite_ids
    };
    callback(payload.skills, skill, data.message);
  }
};

/**
 * A class to put up a modal lightbox. Use setContent to set the DOM element
 * displayed in the lightbox.
 *
 * @class
 */
function Lightbox() {
  this._window = $(window);
  this._container = $('<div class="lightbox"/>');
  this._background = $('<div class="background"/>');
  this._content = $('<div class="content"/>');

  this._container.append(this._background);
  this._container.append(this._content);
  this._container.hide();
}
Lightbox.prototype = {
  /**
   * Set a DOM element to root the lightbox in. Typically will be document.body.
   *
   * @param rootEl {Node}
   */
  bindTo: function(rootEl) {
    $(rootEl).append(this._container);
    return this;
  },
  /**
   * Show the lightbox to the user.
   */
  show: function() {
    this._container.show();
    this._content
        .css('top', Math.max(0, (this._window.height() - this._content.height()) / 2))
        .css('left', Math.max(0, (this._window.width() - this._content.width()) / 2));
    return this;
  },
  /**
   * Close the lightbox and remove it from the DOM.
   */
  close: function() {
    this._container.remove();
    return this;
  },
  /**
   * Set the content shown in the lightbox.
   *
   * @param contentEl {Node or jQuery}
   */
  setContent: function(contentEl) {
    this._content.empty().append(contentEl);
    return this;
  }
};

/**
 * A modal popup with a form to add a new skill.
 *
 * @class
 * @param skillList {SkillList}
 * @param mode {string}
 * @param skillId
 */
function SkillsTableSkillPopup(skillList, mode, skillId) {
  // TODO(broussev): Add jasmine tests.
  var that = this;
  this._skillId = skillId;
  this._skillList = skillList;
  this._skillDisplay = new SkillDisplay(function(skillId) {
    that._onRemoveCallback(skillId);
  });
  this._prerequisiteIds = [];
  this._documentBody = $(document.body);
  this._lightbox = new Lightbox();
  this._createSkillForm = $(
      '<div>' +
      '<h2 class="title"></h2>' +
      '<div class="form-row">' +
      '  <label>Name:</label>' +
      '  <input type="text" class="skill-name">' +
      '</div>' +
      '<div class="form-row">' +
      '  <label>Description:</label>' +
      '  <textarea class="skill-description"></textarea>' +
      '</div>' +
      '<div class="form-row">' +
      '  <label>Prerequisites:</label>' +
      '  <div class="skill-prerequisites"></div>' +
      '</div>' +
      '<div class="inputEx-Field"></div>' +
      '<div>' +
      '  <button class="new-skill-save-button">Save</button>' +
      '  <button class="new-skill-cancel-button">Cancel</button>' +
      '</div>' +
      '</div>');

  this._nameInput = this._createSkillForm.find('.skill-name');
  this._descriptionInput = this._createSkillForm.find('.skill-description');
  this._prerequisitesDiv = this._createSkillForm.find('.skill-prerequisites');
  this._prerequisitesDiv.append(this._skillDisplay.element());
  this._skillDisplay.empty();

  this._skillSelector = new SkillSelector(function(selectedSkills) {
    that._onSkillsSelectedCallback(selectedSkills);
  }, true);
  this._skillSelector.populate(skillList);
  this._skillWidgetDiv = this._createSkillForm.find('.inputEx-Field');
  this._skillWidgetDiv.append(this._skillDisplay.element());
  this._skillWidgetDiv.append(this._skillSelector.element());

  if (mode == 'edit') {
    var skill = this._skillList.getSkillById(skillId);
    var title = 'Edit skill';
    this._nameInput.val(skill.name);
    this._descriptionInput.val(skill.description);
    for (var i = 0; i < skill.prerequisites.length; i++) {
      var prerequisite = this._skillList.getSkillById(
        skill.prerequisites[i].id);
      if (prerequisite) {
        this._prerequisiteIds.push(prerequisite.id);
        this._skillDisplay.add(prerequisite);
      }
    }
  } else {
    var title = 'Add a new skill';
  }

  this._createSkillForm.find('h2.title').text(title);

  this._createSkillForm.find('button.new-skill-save-button').click(function() {
    that._onSave();
    return false;
  });

  this._createSkillForm.find('button.new-skill-cancel-button')
    .click(function() {
      that._onCancel();
      return false;
    }
  );
}

SkillsTableSkillPopup.prototype = {
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
      .setContent(this._createSkillForm)
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

  setName: function(name) {
    this._nameInput.val(name);
    return this;
  },

  _onSave: function() {
    var that = this;
    var name = this._nameInput.val();
    var description = this._descriptionInput.val();
    var prerequisiteIds = this._prerequisiteIds;

    function onSkillCreatedOrUpdated(skills, skill, message) {
      showMsgAutoHide(message);
        that._onAjaxCreateSkillCallback(skills);
      }

    this._skillList.createOrUpdateSkill(onSkillCreatedOrUpdated, name,
      description, prerequisiteIds, that._skillId);
    this._lightbox.close();
  },

  _onCancel: function() {
    this._lightbox.close();
  },

  _onSkillsSelectedCallback: function(selectedSkills) {
    // When new skills are selected in the SkillSelector, update the
    // _prerequisiteIds and repopulate the SkillDisplay.
    var that = this;
    $.each(selectedSkills, function() {
      if (! that._prerequisiteIdsContainSkillId(this.id)) {
        that._prerequisiteIds.push(this.id)
      }
    });
    this._displayPrerequisites();
  },

  _onRemoveCallback: function (skillId) {
    // When a skill is removed from the SkillDisplay,
    // also remove it from the form _prerequisiteIds.
    var that = this;
    var ind = that._prerequisiteIds.indexOf(skillId);
    if (ind > -1) {
      that._prerequisiteIds.splice(ind, 1);
    }
  },

  _displayPrerequisites: function() {
    var that = this;
    this._skillDisplay.empty();
    $.each(that._prerequisiteIds, function() {
      var skill = that._skillList.getSkillById(this);
      if (skill) {
        that._skillDisplay.add(skill);
      }
    });
  },

  _prerequisiteIdsContainSkillId: function(skillId) {
    if ($.inArray(skillId, this._prerequisiteIds) == -1) {
      return false;
    }
    return true;
  }
};

/**
 * A modal popup with a form to add a new skill.
 *
 * @class
 * @param skillList {SkillList}
 */
function LessonEditorSkillPopup(skillList) {
  var that = this;
  this._skillList = skillList;
  this._documentBody = $(document.body);
  this._lightbox = new Lightbox();
  this._createSkillForm = $(
      '<h2>Add a new skill</h2>' +
      '<div class="form-row">' +
      '  <label>Name:</label>' +
      '  <input type="text" class="skill-name">' +
      '</div>' +
      '<div class="form-row">' +
      '  <label>Description:</label>' +
      '  <textarea class="skill-description"></textarea>' +
      '</div>' +
      '<div>' +
      '  <button class="new-skill-save-button">Save</button>' +
      '  <button class="new-skill-cancel-button">Cancel</button>' +
      '</div>');
  this._nameInput = this._createSkillForm.find('.skill-name');
  this._descriptionInput = this._createSkillForm.find('.skill-description');

  this._createSkillForm.find('button.new-skill-save-button').click(function() {
    that._onSave();
    return false;
  });

  this._createSkillForm.find('button.new-skill-cancel-button')
      .click(function() {
        that._onCancel();
        return false;
      });
}

LessonEditorSkillPopup.prototype = {
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
        .setContent(this._createSkillForm)
        .show();
    return this;
  },

  setName: function(name) {
    this._nameInput.val(name);
    return this;
  },

  _onSave: function() {
    var that = this;
    var name = this._nameInput.val();
    var description = this._descriptionInput.val();

    function onSkillCreated(skills, skill, message) {
      showMsgAutoHide(message);
      that._onAjaxCreateSkillCallback(skill);
    }

    this._skillList.createOrUpdateSkill(onSkillCreated, name, description);
    this._lightbox.close();
  },

  _onCancel: function() {
    this._lightbox.close();
  }
};

/**
 * A container to display a list of skills as labels with buttons for removal.
 *
 * @class
 * @param onRemoveCallback {function} Called with the id of a skill whenever a
 *     skill is removed from the view.
 */
function SkillDisplay(onRemoveCallback) {
  this._ol = $('<ol class="skill-display-root"></ol>');
  this._onRemoveCallback = onRemoveCallback;
}

SkillDisplay.prototype = {
  /**
   * Remove all skills from the view.
   *
   * @method
   */
  empty: function() {
    this._ol.empty();
  },

  /**
   * Add a new skill to the view.
   *
   * @method
   * @param skill {object} A skill with id, name, and description.
   */
  add: function(skill) {
    var that = this;
    var skillLi = $('<li class="skill" />');
    var closeButton = $('<button class="close">x</button>');

    skillLi.text(skill.name).append(closeButton);

    closeButton.click(function() {
      skillLi.remove();
      if (that._onRemoveCallback) {
        that._onRemoveCallback(skill.id);
      }
      return false;
    });

    this._ol.append(skillLi);
  },

  /**
   * @return {Element} The root DOM element for the display.
   */
  element: function() {
    return this._ol[0];
  }
};

/**
 * A class to display a widget for skill selection. Enables the user to browse
 * the list of existing skills, or to create a new one.
 *
 * @class
 * @param onSkillsSelectedCallback {function} Callback called with a list of
 *     skills whenever a selection (or creation) is performed.
 */
function SkillSelector(onSkillsSelectedCallback, newSkillDisabled) {
  this._documentBody = $(document.body);
  this._onSkillsSelectedCallback = onSkillsSelectedCallback;
  this._skillList = null;
  var newSkillDiv = newSkillDisabled ? '' :
    '    <div><a class="create" href="#">+ Create new...</a></div>';

  this._rootDiv = $(
    '<div class="skill-selector-root">' +
    '  <button class="add"></button>' +
    '  <div class="selector">' +
    '    <div><input class="search" type="text" placeholder="Skill..."></div>' +
    newSkillDiv +
    '    <ol class="skill-list"></ol>' +
    '    <div><button class="select action">OK</button></div>' +
    '  </div>' +
    '</div>');

  this._addSkillButton = this._rootDiv.find('button.add');
  this._addSkillWidgetDiv = this._rootDiv.find('div.selector');
  this._searchTextInput = this._rootDiv.find('input.search');
  this._createNewSkillButton = this._rootDiv.find('a.create');
  this._selectNewSkillButton = this._rootDiv.find('button.select');
  this._selectSkillListOl = this._rootDiv.find('ol.skill-list');

  this._selectNewSkillButton.prop('disabled', true);

  this._bind();
  this._close();
}

SkillSelector.prototype = {
  /**
   * @method
   * @return {Element} The root DOM element for the selector.
   */
  element: function() {
    return this._rootDiv[0];
  },
  /**
   * Populate the drop-down skill chooser with the list of avaiable skills.
   * @method
   * @param skillList {SkillList}
   */
  populate: function(skillList) {
    this._skillList = skillList;
    this._rebuildSelector();
  },
  _bind: function() {
    var that = this;

    this._addSkillButton.click(function() {
      that._addSkillWidgetDiv.show();
      return false;
    });

    this._documentBody.click(function(evt) {
      if ($(evt.target).closest('div.selector').length == 0) {
        that._close();
      }
    });

    this._searchTextInput.keyup(function(evt) {
      that._filterAddSkillWidget(that._searchTextInput.val());
    });

    this._createNewSkillButton.click(function() {
      that._openLessonEditorSkillPopup();
      that._close();
      return false;
    });

    this._selectNewSkillButton.click(function() {
      that._selectSkills();
      that._close();
      return false;
    });

  },
  _close: function() {
    this._addSkillWidgetDiv.hide();
    this._searchTextInput.val('');
    this._selectSkillListOl.find('li').show();
    this._addSkillWidgetDiv.find('input.skill-select').prop('checked', false);
    this._selectNewSkillButton.prop('disabled', true);
  },

  _rebuildSelector: function() {
    var that = this;
    this._selectSkillListOl.empty();
    this._skillList.eachSkill(function(skill) {
      that._addSkillToSelector(skill);
    });
  },

  _addSkillToSelector: function(skill) {
    var that = this;
    var skillLi = $('<li/>');
    var label = $('<label></label>');
    var checkbox = $('<input type="checkbox" class="skill-select">');

    checkbox.change(function() {
      if (that._addSkillWidgetDiv.find('input.skill-select:checked').length) {
        that._selectNewSkillButton.prop('disabled', false);
      } else {
        that._selectNewSkillButton.prop('disabled', true);
      }
    });

    checkbox.data('id', skill.id);

    label.append(checkbox);
    label.append($('<span></span>').text(skill.name));

    skillLi.append(label);
    this._selectSkillListOl.append(skillLi);
  },

  _filterAddSkillWidget: function(filter) {
    filter = filter.toLowerCase();
    this._selectSkillListOl.find('> li').show();
    this._selectSkillListOl.find('> li span').each(function() {
      if ($(this).text().toLowerCase().indexOf(filter) == -1) {
        $(this).closest('li').hide();
      }
    });
  },

  _openLessonEditorSkillPopup: function() {
    var that = this;
    new LessonEditorSkillPopup(this._skillList)
      .setName(this._searchTextInput.val())
      .open(function(skill) {
        that._rebuildSelector();
        if (that._onSkillsSelectedCallback) {
          that._onSkillsSelectedCallback([skill])
        }
      });
  },

  _selectSkills: function() {
    var that = this;
    var selectedSkills = this._addSkillWidgetDiv
        .find('input.skill-select:checked')
        .map(function() {
          var skillId = $(this).data('id');
          return that._skillList.getSkillById(skillId);
        });
    this._onSkillsSelectedCallback(selectedSkills);
  }
};

function SkillEditorForOeditor(env) {
  var that = this;

  this._env = env;
  this._skillList = new SkillList();

  this._skillDisplay = new SkillDisplay(function(skillId) {
    that._onRemoveCallback(skillId);
  });
  this._skillSelector = new SkillSelector(function(skillList) {
    that._onSkillsSelectedCallback(skillList);
  });

  this._skillWidgetDiv = $('<div class="inputEx-Field"></div>');
  this._skillWidgetDiv.append(this._skillDisplay.element());
  this._skillWidgetDiv.append(this._skillSelector.element());
}
SkillEditorForOeditor.prototype = {
  element: function() {
    return this._skillWidgetDiv;
  },
  init: function() {
    var that = this;
    this._skillList.load(function() {
      that._populateSkillList();
      that._skillSelector.populate(that._skillList);
    });
  },
  _onSkillsSelectedCallback: function(skillList) {
    // When new skills are selected in the SkillSelector, update the OEditor
    // form and repopulate the SkillDisplay.
    var that = this;
    $.each(skillList, function() {
      if (! that._formContainsSkillId(this.id)) {
        that._env.form.inputsNames.skills.addElement({'skill': this.id});
      }
    });
    this._populateSkillList();
  },
  _onRemoveCallback: function (skillId) {
    // When a skill is removed from the SkillDisplay, also remove it from the
    // OEditor form.
    var that = this;
    $.each(this._env.form.inputsNames.skills.subFields, function(i) {
      var id = this.inputsNames.skill.getValue();
      if (id === skillId) {
        that._env.form.inputsNames.skills.removeElement(i);
        return false;
      }
    });
  },
  _populateSkillList: function() {
    // Populate the SkillDisplay with the skills in the OEditor form.
    var that = this;
    this._skillDisplay.empty();
    $.each(this._env.form.inputsNames.skills.subFields, function() {
      var id = this.inputsNames.skill.getValue();
      var skill = that._skillList.getSkillById(id);
      if (skill) {
        that._skillDisplay.add(skill);
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
 * Export the classes which will be used in global scope.
 */
window.SkillEditorForOeditor = SkillEditorForOeditor;
window.SkillList = SkillList;
window.SkillTable = SkillTable;
