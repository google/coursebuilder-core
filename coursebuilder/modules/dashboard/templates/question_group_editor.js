var EMPTY_LIST_MESSAGE = 'There are no questions available to add to this ' +
    'group.';

$('.question-group-items.empty-question-list')
    .hide()
    .after($('<div class="empty-question-list-message"></div>')
        .text(EMPTY_LIST_MESSAGE));
