(function () {
  'use strict';

  function initBlurSave() {
    // Review-response textareas use hx-trigger='blur' — htmx re-processes
    // them automatically on htmx:afterSwap. No extra JS needed here.
    // Todo pill inputs and comment block textareas wire their own blur
    // handler when opened via openTodoEdit / openCommentEdit (idempotent).
  }
  document.addEventListener('DOMContentLoaded', initBlurSave);
  document.body.addEventListener('htmx:afterSwap', initBlurSave);

  var ICONS = { saved: '✓', dirty: '〇', saving: '⏳', error: '⚠', '': '' };

  function setStatusFor(ta, st, msg) {
    if (!ta) return;
    ta.dataset.saveStatus = st;
    var area = ta.parentElement;
    if (!area) return;
    var indicator = area.querySelector('.save-indicator');
    if (!indicator) return;
    indicator.className = 'save-indicator status-' + st;
    indicator.title = msg || '';
    indicator.textContent = ICONS[st] !== undefined ? ICONS[st] : '';
  }

  var _indicatorEventsWired = false;

  function wireIndicatorDocumentEvents() {
    if (_indicatorEventsWired) return;
    _indicatorEventsWired = true;

    document.addEventListener('htmx:beforeRequest', function (e) {
      var el = e.detail && e.detail.elt;
      if (el && el.classList && el.classList.contains('review-response-textarea')) {
        setStatusFor(el, 'saving');
      }
    });

    document.addEventListener('htmx:afterRequest', function (e) {
      var el = e.detail && e.detail.elt;
      if (!el || !el.classList || !el.classList.contains('review-response-textarea')) return;
      if (e.detail.successful) {
        setStatusFor(el, 'saved');
      } else {
        var msg = 'Save failed';
        try {
          var d = JSON.parse(e.detail.xhr && e.detail.xhr.responseText);
          if (d && d.detail) msg = d.detail;
        } catch (ex) {}
        setStatusFor(el, 'error', msg);
      }
    });
  }

  function updateMtimeForFile(file, mtime) {
    if (!file) return;
    var mtimeStr = String(mtime);
    var esc = (window.CSS && CSS.escape) ? CSS.escape(file) : file.replace(/"/g, '\\"');
    document.querySelectorAll('li[data-file="' + esc + '"]').forEach(function (li) {
      li.dataset.mtime = mtimeStr;
      li.querySelectorAll('.review-item').forEach(function (item) {
        var ta = item.querySelector('textarea.review-response-textarea');
        if (ta) ta.dataset.mtime = mtimeStr;
        var hidden = item.querySelector('input[name="mtime"]');
        if (hidden) hidden.value = mtimeStr;
      });
      var markHidden = li.querySelector('.mark-without-responses input[name="mtime"]');
      if (markHidden) markHidden.value = mtimeStr;
    });
    document.querySelectorAll('.comment-block[data-file="' + esc + '"]').forEach(function (block) {
      block.dataset.mtime = mtimeStr;
    });
  }

  function handleMtimeBroadcast(evt) {
    var d = evt && evt.detail;
    if (!d || !d.file) return;
    updateMtimeForFile(d.file, d.mtime);
  }

  document.body.addEventListener('responsesaved', handleMtimeBroadcast);
  document.body.addEventListener('allreviewed', handleMtimeBroadcast);
  document.body.addEventListener('reviewsaved', handleMtimeBroadcast);
  document.body.addEventListener('commentssaved', handleMtimeBroadcast);
  document.body.addEventListener('todosaved', handleMtimeBroadcast);

  // htmx auto-fires events from HX-Trigger response headers, but direct
  // fetch() doesn't. Replay them manually so sibling blocks on the same
  // file (e.g. a second comment block whose editor was opened after the
  // first save) get their data-mtime refreshed via handleMtimeBroadcast.
  function dispatchHxTriggers(headers) {
    if (!headers) return;
    var raw = headers.get && headers.get('HX-Trigger');
    if (!raw) return;
    var parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (e) {
      parsed = null;
    }
    if (parsed && typeof parsed === 'object') {
      Object.keys(parsed).forEach(function (name) {
        document.body.dispatchEvent(new CustomEvent(name, { detail: parsed[name], bubbles: true }));
      });
    } else {
      document.body.dispatchEvent(new CustomEvent(raw, { bubbles: true }));
    }
  }

  function initSaveIndicators() {
    document.querySelectorAll('.review-response-textarea').forEach(function (ta) {
      if (ta.dataset.indicatorInited) return;
      ta.dataset.indicatorInited = '1';

      var area = ta.parentElement;
      var indicator = area.querySelector('.save-indicator');
      if (!indicator) {
        indicator = document.createElement('span');
        indicator.className = 'save-indicator';
        area.appendChild(indicator);
      }

      setStatusFor(ta, ta.dataset.saveStatus || '');

      ta.addEventListener('input', function () { setStatusFor(ta, 'dirty'); });

      ta.addEventListener('blur', function () {
        if (ta.dataset.saveStatus === 'dirty') {
          setStatusFor(ta, 'saving');
          setTimeout(function () {
            if (ta.dataset.saveStatus === 'saving') {
              setStatusFor(ta, 'dirty');
            }
          }, 300);
        }
      });
    });
    wireIndicatorDocumentEvents();
  }
  document.addEventListener('DOMContentLoaded', initSaveIndicators);
  document.body.addEventListener('htmx:afterSwap', initSaveIndicators);

  function flushDirtyTextareas() {
    document.querySelectorAll('.review-response-textarea').forEach(function (ta) {
      // Re-send mid-flight saves cancelled by tab switch — server mtime guard makes it idempotent
      if (ta.dataset.saveStatus !== 'dirty' && ta.dataset.saveStatus !== 'saving') return;

      var data = new URLSearchParams();
      data.append('file_path', ta.dataset.file);
      data.append('index', ta.dataset.index);
      data.append('response_text', ta.value);
      data.append('mtime', ta.dataset.mtime);
      var item = ta.closest('.review-item');
      if (item && item.id) data.append('wrapper_id', item.id);

      // Use fetch with keepalive so the wrapped fetch in base.html attaches
      // the CSRF header. sendBeacon can't set custom headers and would be
      // rejected by CSRF middleware.
      if (document.visibilityState === 'hidden') {
        ta.dataset.saveStatus = 'saving';
        fetch('/edit/review-response', {
          method: 'PATCH',
          body: data,
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          keepalive: true
        }).catch(function () {});
      } else {
        setStatusFor(ta, 'saving');
        fetch('/edit/review-response', {
          method: 'PATCH',
          body: data,
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
        }).then(function (r) {
          if (r.ok) {
            r.text().then(function (html) {
              var tmp = document.createElement('template');
              tmp.innerHTML = html;
              var newEl = tmp.content.firstElementChild;
              if (newEl && item) {
                item.replaceWith(newEl);
                if (window.htmx) window.htmx.process(newEl);
              }
            });
          }
        }).catch(function () {});
      }
    });
  }

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') {
      flushDirtyTextareas();
    }
  });

  window.addEventListener('pagehide', function () {
    flushDirtyTextareas();
  });

  window.addEventListener('beforeunload', function (e) {
    var anyDirty = false;
    document.querySelectorAll('.review-response-textarea').forEach(function (ta) {
      if (ta.dataset.saveStatus === 'dirty' || ta.dataset.saveStatus === 'saving') {
        anyDirty = true;
      }
    });
    if (anyDirty) {
      e.preventDefault();
      e.returnValue = 'You have unsaved responses — are you sure you want to leave?';
      return e.returnValue;
    }
  });

  window.flashToast = function (msg, kind, duration) {
    var container = document.getElementById('toast-container');
    if (!container) return;
    var toast = document.createElement('div');
    toast.className = 'toast toast-' + (kind || 'success');
    toast.textContent = msg;
    container.appendChild(toast);
    var ms = (typeof duration === 'number') ? duration : 1500;
    setTimeout(function () {
      toast.style.opacity = '0';
      setTimeout(function () { toast.remove(); }, 250);
    }, ms);
  };

  window.openTodoEdit = function (el) {
    var li = el.closest('.todo-item');
    if (!li || li.dataset.editing === '1') return;
    li.dataset.editing = '1';

    var pill = li.querySelector('.todo-pill');
    var checkbox = li.querySelector('.todo-checkbox');
    var text = li.querySelector('.todo-text');
    var editBtn = li.querySelector('.todo-edit-btn');

    var currentContent = pill ? pill.textContent :
      (checkbox && checkbox.checked ? 'x' : '');

    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'todo-edit-input';
    input.value = currentContent;
    input.style.width = '10em';
    input.style.marginRight = '0.5em';

    var replaced = pill || checkbox;
    replaced.style.display = 'none';
    li.insertBefore(input, replaced);
    input.focus();
    input.select();

    var restored = false;
    function restore() {
      if (restored) return;
      restored = true;
      input.remove();
      replaced.style.display = '';
      delete li.dataset.editing;
    }

    function save() {
      if (restored) return;
      var newContent = input.value;
      if (newContent === currentContent) { restore(); return; }
      var form = new FormData();
      form.append('file', li.dataset.file);
      form.append('line', li.dataset.line);
      form.append('hash', li.dataset.hash);
      form.append('new_content', newContent);
      restored = true;
      delete li.dataset.editing;
      fetch('/edit/todo', { method: 'PATCH', body: form })
        .then(function (r) {
          return r.text().then(function (body) { return { ok: r.ok, status: r.status, body: body }; });
        })
        .then(function (res) {
          if (res.ok) {
            var tmp = document.createElement('template');
            tmp.innerHTML = res.body.trim();
            var newEl = tmp.content.firstElementChild;
            if (newEl) {
              li.replaceWith(newEl);
              if (window.htmx) window.htmx.process(newEl);
            }
            window.flashToast('Saved');
          } else {
            var tmp = document.createElement('template');
            tmp.innerHTML = res.body.trim();
            var oob = tmp.content.querySelector('#toast-container');
            if (oob) {
              var t = oob.firstElementChild;
              if (t) document.getElementById('toast-container').appendChild(t);
            } else {
              window.flashToast('File changed on disk — refresh.', 'error');
            }
            input.remove();
            replaced.style.display = '';
          }
        })
        .catch(function () {
          window.flashToast('Network error', 'error');
          input.remove();
          replaced.style.display = '';
        });
    }

    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); save(); }
      else if (e.key === 'Escape') { e.preventDefault(); restore(); }
    });
    input.addEventListener('blur', save);
  };

  window.openCommentEdit = function (el) {
    var block = el.closest('.comment-block');
    if (!block || block.dataset.editing === '1') return;
    block.dataset.editing = '1';

    var raw = block.dataset.raw || '';
    var bq = block.querySelector('blockquote');
    bq.style.display = 'none';

    var wrap = document.createElement('div');
    wrap.className = 'comment-edit';

    var ta = document.createElement('textarea');
    ta.value = raw;
    wrap.appendChild(ta);

    var actions = document.createElement('div');
    actions.className = 'actions';

    var saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.textContent = 'Save';
    saveBtn.className = 'primary';

    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.className = 'secondary outline';

    actions.appendChild(saveBtn);
    actions.appendChild(cancelBtn);
    wrap.appendChild(actions);

    block.appendChild(wrap);
    ta.focus();

    function restore() {
      wrap.remove();
      bq.style.display = '';
      delete block.dataset.editing;
    }

    cancelBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      restore();
    });

    saveBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      var form = new FormData();
      form.append('file', block.dataset.file);
      form.append('block_start', block.dataset.start);
      form.append('block_end', block.dataset.end);
      form.append('new_content', ta.value);
      // Read mtime at click time so a save that follows another save on the
      // same file picks up the broadcasted post-save mtime.
      form.append('mtime', block.dataset.mtime);
      if (block.dataset.marker) {
        form.append('marker', block.dataset.marker);
      }
      fetch('/edit/comments', { method: 'PATCH', body: form })
        .then(function (r) {
          return r.text().then(function (body) {
            return { ok: r.ok, status: r.status, body: body, headers: r.headers };
          });
        })
        .then(function (res) {
          if (res.ok) {
            var tmp = document.createElement('template');
            tmp.innerHTML = res.body.trim();
            var newEl = tmp.content.firstElementChild;
            if (newEl) {
              block.replaceWith(newEl);
              if (window.htmx) window.htmx.process(newEl);
            }
            // dispatchHxTriggers fires `commentssaved`, which the toast
            // listener in base.html turns into the "Saved" toast.
            dispatchHxTriggers(res.headers);
          } else {
            var tmp = document.createElement('template');
            tmp.innerHTML = res.body.trim();
            var oob = tmp.content.querySelector('#toast-container');
            if (oob) {
              var t = oob.firstElementChild;
              if (t) document.getElementById('toast-container').appendChild(t);
            } else {
              window.flashToast('File changed on disk — refresh.', 'error');
            }
            restore();
          }
        })
        .catch(function () {
          window.flashToast('Network error', 'error');
          restore();
        });
    });

    // Clicking inside the textarea shouldn't retrigger open
    wrap.addEventListener('click', function (e) { e.stopPropagation(); });
  };
})();
