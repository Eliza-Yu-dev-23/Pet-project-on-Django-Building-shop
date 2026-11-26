(function () {
    'use strict';

    var treeEl = document.getElementById('org-tree');
    var panel = document.getElementById('org-panel');
    if (!treeEl || !panel || !window.jQuery || !jQuery.jstree) {
        return;
    }

    var $tree = jQuery(treeEl);
    var treeUrl = treeEl.getAttribute('data-tree-url');
    var unassignedUrl = panel.getAttribute('data-unassigned-url');

    var escapeMap = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    };

    function esc(value) {
        return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, function (char) {
            return escapeMap[char];
        });
    }

    function initials(name) {
        var parts = String(name || '').trim().split(/\s+/).filter(Boolean);
        if (!parts.length) {
            return '—';
        }
        if (parts.length === 1) {
            return parts[0].slice(0, 2).toUpperCase();
        }
        return (parts[0].charAt(0) + parts[1].charAt(0)).toUpperCase();
    }

    function roleBadge(role) {
        var isAdmin = role === 'Администратор';
        return '<span class="role-badge ' + (isAdmin ? 'role-admin' : 'role-employee') + '">' +
            esc(role || 'Без роли') + '</span>';
    }

    function statusDot(active) {
        return active
            ? '<span class="status-dot status-on">Активен</span>'
            : '<span class="status-dot status-off">Неактивен</span>';
    }

    function avatar(name, extraClass) {
        return '<span class="avatar ' + (extraClass || '') + '">' + esc(initials(name)) + '</span>';
    }

    function miniStat(value, label) {
        return '<div class="mini-stat"><span class="mini-stat-value">' + esc(value) + '</span>' +
            '<span class="mini-stat-label">' + esc(label) + '</span></div>';
    }

    function bossCard(boss) {
        return '<div class="boss-card">' +
            avatar(boss.name, 'avatar-lg') +
            '<div class="boss-main">' +
            '<strong>' + esc(boss.name) + '</strong>' +
            '<div class="muted">@' + esc(boss.login) + '</div>' +
            roleBadge(boss.role) +
            '</div>' +
            statusDot(boss.active) +
            '</div>';
    }

    function employeeRow(employee) {
        return '<div class="employee-item">' +
            avatar(employee.name) +
            '<div class="employee-main">' +
            '<strong>' + esc(employee.name) + '</strong>' +
            '<small>@' + esc(employee.login) + ' · ' + esc(employee.department) + '</small>' +
            '</div>' +
            roleBadge(employee.role) +
            '</div>';
    }

    function employeeList(employees) {
        if (!employees || !employees.length) {
            return '<div class="empty-inline">Сотрудников нет</div>';
        }
        return '<div class="employee-list">' + employees.map(employeeRow).join('') + '</div>';
    }

    function showLoading() {
        panel.innerHTML = '<div class="panel-loading"><span class="loader"></span><p>Загружаем данные…</p></div>';
    }

    function showError() {
        panel.innerHTML = '<div class="panel-loading"><div class="panel-placeholder-icon">⚠️</div>' +
            '<p>Не удалось загрузить данные. Попробуйте выбрать элемент ещё раз.</p></div>';
    }

    function renderDepartment(data) {
        panel.innerHTML =
            '<div class="panel-head">' +
            '<div class="panel-icon">🏢</div>' +
            '<div>' +
            '<div class="panel-kicker">Департамент</div>' +
            '<h2>' + esc(data.name) + '</h2>' +
            '<div class="panel-path">' + esc(data.parent_path) + '</div>' +
            '</div>' +
            '</div>' +
            '<div class="panel-stat-grid">' +
            miniStat(data.subdepartment_count, 'подчинённых департаментов') +
            miniStat(data.employee_count, 'сотрудников в подчинении') +
            miniStat(data.direct_employee_count, 'прямых сотрудников') +
            '</div>' +
            '<h3 class="panel-section-title">Руководитель</h3>' +
            (data.boss ? bossCard(data.boss) : '<div class="empty-inline">Руководитель не назначен</div>') +
            '<h3 class="panel-section-title">Прямые сотрудники</h3>' +
            employeeList(data.direct_employees);
    }

    function renderUser(data) {
        var headed = '';
        if (data.headed_departments && data.headed_departments.length) {
            headed = '<div class="dept-chips">' + data.headed_departments.map(function (name) {
                return '<span class="chip">' + esc(name) + '</span>';
            }).join('') + '</div>';
        } else {
            headed = '<div class="empty-inline">Не является руководителем департаментов</div>';
        }

        panel.innerHTML =
            '<div class="panel-head">' +
            avatar(data.name, 'avatar-xl') +
            '<div>' +
            '<div class="panel-kicker">Сотрудник</div>' +
            '<h2>' + esc(data.name) + '</h2>' +
            '<div class="panel-path">@' + esc(data.login) + '</div>' +
            '</div>' +
            '</div>' +
            '<div class="panel-stat-grid panel-stat-grid-2">' +
            '<div class="mini-stat"><span class="mini-stat-label">Роль</span><span class="mini-stat-value" style="font-size:15px">' +
            esc(data.role) + '</span></div>' +
            '<div class="mini-stat"><span class="mini-stat-label">Департамент</span><span class="mini-stat-value" style="font-size:15px">' +
            esc(data.department) + '</span></div>' +
            '<div class="mini-stat"><span class="mini-stat-label">Статус</span><span class="mini-stat-value" style="font-size:15px">' +
            (data.active ? 'Активен' : 'Неактивен') + '</span></div>' +
            '<div class="mini-stat"><span class="mini-stat-label">Проверок контрагентов</span><span class="mini-stat-value">' +
            esc(data.checks_count) + '</span></div>' +
            '</div>' +
            '<h3 class="panel-section-title">Руководит департаментами</h3>' +
            headed;
    }

    function renderGroup(data) {
        panel.innerHTML =
            '<div class="panel-head">' +
            '<div class="panel-icon">👥</div>' +
            '<div>' +
            '<div class="panel-kicker">Группа</div>' +
            '<h2>' + esc(data.name) + '</h2>' +
            '<div class="panel-path">Сотрудники без привязки к департаменту</div>' +
            '</div>' +
            '</div>' +
            '<div class="panel-stat-grid panel-stat-grid-1">' +
            miniStat(data.employee_count, 'сотрудников') +
            '</div>' +
            '<h3 class="panel-section-title">Сотрудники</h3>' +
            employeeList(data.employees);
    }

    function loadJson(url) {
        return fetch(url, {
            headers: { 'Accept': 'application/json' },
            credentials: 'same-origin'
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            return response.json();
        });
    }

    $tree.jstree({
        core: {
            data: {
                url: treeUrl,
                dataType: 'json',
                type: 'GET',
                data: function (node) {
                    return { id: node.id };
                }
            },
            themes: { dots: true, icons: true },
            multiple: false
        },
        types: {
            department: { icon: 'org-icon-dept' },
            user: { icon: 'org-icon-user' },
            group: { icon: 'org-icon-group' }
        },
        plugins: ['types', 'wholerow']
    });

    $tree.on('ready.jstree', function () {
        var roots = $tree.jstree('get_json', '#', { flat: false });
        if (roots && roots.length) {
            $tree.jstree('open_node', roots[0].id);
        }
    });

    $tree.on('select_node.jstree', function (event, data) {
        var node = data.node;

        if (node.id === 'dept_none') {
            showLoading();
            loadJson(unassignedUrl)
                .then(renderGroup)
                .catch(showError);
            return;
        }

        var match = /^(dept|user)_(\d+)$/.exec(node.id);
        if (!match) {
            return;
        }

        var url = match[1] === 'dept'
            ? '/org/departments/' + match[2] + '/info/'
            : '/org/users/' + match[2] + '/info/';

        showLoading();
        loadJson(url)
            .then(function (payload) {
                if (payload.kind === 'department') {
                    renderDepartment(payload);
                } else if (payload.kind === 'user') {
                    renderUser(payload);
                } else {
                    renderGroup(payload);
                }
            })
            .catch(showError);
    });
})();
