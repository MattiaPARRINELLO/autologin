from checkmate_watcher.status_ui import STATUS_HTML


def test_la_modale_des_nouveautes_est_accessible():
    assert 'id="releaseLayer"' in STATUS_HTML
    assert 'role="dialog"' in STATUS_HTML
    assert 'aria-modal="true"' in STATUS_HTML
    assert 'aria-labelledby="releaseTitle"' in STATUS_HTML
    assert "prefers-reduced-motion" in STATUS_HTML
    assert 'action: "dismiss-release"' in STATUS_HTML


def test_les_contenus_distants_sont_inseres_en_texte():
    assert "element.textContent = text ||" in STATUS_HTML
    assert "metrics.replaceChildren()" in STATUS_HTML
    assert "features.replaceChildren()" in STATUS_HTML


def test_l_animation_des_performances_reduit_les_barres():
    assert 'id="releasePerformance"' in STATUS_HTML
    assert "release-performance-drop" in STATUS_HTML
    assert "animatePerformance" in STATUS_HTML
    assert "prefers-reduced-motion" in STATUS_HTML
