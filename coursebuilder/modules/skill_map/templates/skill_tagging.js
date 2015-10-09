$(function() {
  // Create a new skill editor widget and move the div.skill-panel (and thus
  // the description it contains) to just after the buttons in that new widget.
  var skillPanelDiv = $('div.skill-panel');
  var skillEditorForOeditor = new SkillEditorForOeditor(cb_global);

  // Insert the skill editor widget into the parent of the skill panel,
  // just before the current location of the skill panel.
  skillPanelDiv.before(skillEditorForOeditor.element());

  // Re-parent the skill panel *inside* the new skill editor widget,
  // just after the existing widget elements (skill display list, Add and
  // Create buttons), so the description is last and properly left-aligns.
  skillEditorForOeditor.element().append(skillPanelDiv);

  skillEditorForOeditor.init();
});
