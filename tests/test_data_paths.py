from data_paths import DataPaths


def test_data_root_is_explicit_and_all_artifacts_share_it(tmp_path):
    paths = DataPaths.from_env({"ASHARE_DATA_ROOT": str(tmp_path)})

    assert paths.root == tmp_path.resolve()
    assert paths.watchlist_file("2026-08-20").parent == paths.root
    assert paths.positions_file().parent == paths.root
    assert paths.perf_tracker_file().parent == paths.root
    assert paths.index_pairs_file().parent == paths.root
    assert paths.reports_dir().parent == paths.root

