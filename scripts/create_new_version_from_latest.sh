#!/bin/bash
#
# Create a new version (for a release) of the documentation from _docs/_latest/.
# Add the new version to (1) Jekyll config, (2) the docs categories data struct-
# ure, (3) the _docs/ directory, and (4) the _includes/docs/ directory. Also,
# update all links to latest to point to the new version created.

RELEASE_VERSION="$1"

err() {
  echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')]: $@" >&2
}

#######################################
# Check if Jekyll config has defaults
# for version directories.
# Globals:
#   RELEASE_VERSION
# Arguments:
#   None
# Returns:
#   string - "true" or "false"
#######################################
function config_has_version() {
    yq '[.defaults[].scope.path == "_docs/'${RELEASE_VERSION}'"] | any' \
        _config.yml
}

#######################################
# Return the last associative key used
# at the top-level of Jekyll config.
# Globals:
#   None
# Arguments:
#   None
# Returns:
#   string - last key
#######################################
function last_config_key() {
    yq -r '. | keys_unsorted | last' _config.yml
}

#######################################
# Adds defaults for new version to
# Jekyll config file.
# Globals:
#   RELEASE_VERSION
# Arguments:
#   None
# Returns:
#   None
#######################################
function add_version_to_config() {
    echo "$(cat _config.yml <(cat scripts/data/version_config_defaults.yml | \
        sed -e s/'\$\$VERSION\$\$'/${RELEASE_VERSION}/g))" > _config.yml
}

function snapshot_docs() {
    cp -R _docs/_latest/ _docs/${RELEASE_VERSION}
}

function doc_categories_has_version() {
    yq '. | has("'${RELEASE_VERSION}'")' _data/doc_categories.yml
}

#######################################
# Check if version is present in the
# documentation categories.
# Globals:
#   RELEASE_VERSION
# Arguments:
#   None
# Returns:
#   string - "true" or "false"
#######################################
function snapshot_doc_categories() {
    echo "$(yq -y '. += {"'${RELEASE_VERSION}'": .latest}' _data/doc_categories.yml)" \
        > _data/doc_categories.yml
}

#######################################
# Update all Jekyll links/includes that
# reference 'latest' docs in docs.
# Globals:
#   RELEASE_VERSION
# Arguments:
#   None
# Returns:
#   None
#######################################
function update_docs_links() {
    find _docs/${RELEASE_VERSION} -type f -exec \
        sed -i s:_docs/_latest:_docs/${RELEASE_VERSION}:g {} +
    find _docs/${RELEASE_VERSION} -type f -exec \
        sed -i s:docs/_latest:docs/${RELEASE_VERSION}:g {} +
    find _docs/${RELEASE_VERSION} -type f -exec \
        sed -i s:_docs/latest:_docs/${RELEASE_VERSION}:g {} +
    find _docs/${RELEASE_VERSION} -type f -exec \
        sed -i s:docs/latest:docs/${RELEASE_VERSION}:g {} +
}

function snapshot_includes() {
    cp -R _includes/docs/latest/ _includes/docs/${RELEASE_VERSION}
}

#######################################
# Update all Jekyll links/includes that
# reference 'lastest' docs in includes.
# Globals:
#   RELEASE_VERSION
# Arguments:
#   None
# Returns:
#   None
#######################################
function update_includes_links() {
    find _includes/docs/${RELEASE_VERSION} -type f -exec \
        sed -i s:_docs/_latest:_docs/${RELEASE_VERSION}:g {} +
    find _includes/docs/${RELEASE_VERSION} -type f -exec \
        sed -i s:docs/_latest:docs/${RELEASE_VERSION}:g {} +
    find _includes/docs/${RELEASE_VERSION} -type f -exec \
        sed -i s:_docs/latest:_docs/${RELEASE_VERSION}:g {} +
}

function main() {
    if [ "$(config_has_version)" = "true" ]; then
        echo "Version '${RELEASE_VERSION}' is already present in _config.yml."
        exit 0
    fi

    if [ "$(last_config_key)" != "defaults" ]; then
        err "Error: Please make sure that \"defaults\" is the last configuration 
            block in _config.yml"
        exit -1
    fi

    echo "Adding '${RELEASE_VERSION}' to _config.yml ..."
    add_version_to_config

    if [ "$(doc_categories_has_version)" = "true" ]; then
        echo "Version '${RELEASE_VERSION}' is already present in 
            _data/doc_categories.yml."
        echo "Please update by hand, if necessary."
    else
        echo "Snapshotting latest doc categories in '_data/doc_categories.yml'
            for ${RELEASE_VERSION} ..."
        snapshot_doc_categories
    fi

    echo "Snapshotting latest docs to '_docs/${RELEASE_VERSION}/' ..."
    snapshot_docs

    echo "Updating site links within '_docs/${RELEASE_VERSION}/' ..."
    update_docs_links

    echo "Snapshotting latest includes to '_includes/docs/${RELEASE_VERSION}' ..."
    snapshot_includes

    echo "Updating site links within '_includes/docs/${RELEASE_VERSION}' ..."
    update_includes_links

    echo "DONE."
}

main "$@"