"""Canonical problem-set definitions — single source of truth for code and docs.

When a track name or problem list changes, update it HERE.  Everything else
(seed.py, README, CLAUDE.md, spec) references this file.
"""

from __future__ import annotations

# ── Track names ───────────────────────────────────────────────────────────────

ALGO_TRACK_NAME = "LeetCode Top Interview 150"
SQL_TRACK_NAME = "SQL 50"

# ── Problem lists ─────────────────────────────────────────────────────────────
# Each entry: (slug, pattern)
# order_index is implicit (1-based position within each list)

ALGO_PROBLEMS: list[tuple[str, str]] = [
    # Array / String
    ("merge-sorted-array", "Array / String"),
    ("remove-element", "Array / String"),
    ("remove-duplicates-from-sorted-array", "Array / String"),
    ("remove-duplicates-from-sorted-array-ii", "Array / String"),
    ("majority-element", "Array / String"),
    ("rotate-array", "Array / String"),
    ("best-time-to-buy-and-sell-stock", "Array / String"),
    ("best-time-to-buy-and-sell-stock-ii", "Array / String"),
    ("jump-game", "Array / String"),
    ("jump-game-ii", "Array / String"),
    ("h-index", "Array / String"),
    ("insert-delete-getrandom-o1", "Array / String"),
    ("product-of-array-except-self", "Array / String"),
    ("gas-station", "Array / String"),
    ("candy", "Array / String"),
    ("trapping-rain-water", "Array / String"),
    ("roman-to-integer", "Array / String"),
    ("integer-to-roman", "Array / String"),
    ("length-of-last-word", "Array / String"),
    ("longest-common-prefix", "Array / String"),
    ("reverse-words-in-a-string", "Array / String"),
    ("zigzag-conversion", "Array / String"),
    ("find-the-index-of-the-first-occurrence-in-a-string", "Array / String"),
    ("text-justification", "Array / String"),
    # Two Pointers
    ("valid-palindrome", "Two Pointers"),
    ("is-subsequence", "Two Pointers"),
    ("two-sum-ii-input-array-is-sorted", "Two Pointers"),
    ("container-with-most-water", "Two Pointers"),
    ("3sum", "Two Pointers"),
    # Sliding Window
    ("minimum-size-subarray-sum", "Sliding Window"),
    ("longest-substring-without-repeating-characters", "Sliding Window"),
    ("substring-with-concatenation-of-all-words", "Sliding Window"),
    ("minimum-window-substring", "Sliding Window"),
    # Matrix
    ("valid-sudoku", "Matrix"),
    ("spiral-matrix", "Matrix"),
    ("rotate-image", "Matrix"),
    ("set-matrix-zeroes", "Matrix"),
    ("game-of-life", "Matrix"),
    # Hashmap
    ("ransom-note", "Hashmap"),
    ("isomorphic-strings", "Hashmap"),
    ("word-pattern", "Hashmap"),
    ("valid-anagram", "Hashmap"),
    ("group-anagrams", "Hashmap"),
    ("two-sum", "Hashmap"),
    ("happy-number", "Hashmap"),
    ("contains-duplicate-ii", "Hashmap"),
    ("longest-consecutive-sequence", "Hashmap"),
    # Intervals
    ("summary-ranges", "Intervals"),
    ("merge-intervals", "Intervals"),
    ("insert-interval", "Intervals"),
    ("minimum-number-of-arrows-to-burst-balloons", "Intervals"),
    # Stack
    ("valid-parentheses", "Stack"),
    ("simplify-path", "Stack"),
    ("min-stack", "Stack"),
    ("evaluate-reverse-polish-notation", "Stack"),
    ("basic-calculator", "Stack"),
    # Linked List
    ("linked-list-cycle", "Linked List"),
    ("add-two-numbers", "Linked List"),
    ("merge-two-sorted-lists", "Linked List"),
    ("copy-list-with-random-pointer", "Linked List"),
    ("reverse-linked-list-ii", "Linked List"),
    ("reverse-nodes-in-k-group", "Linked List"),
    ("remove-nth-node-from-end-of-list", "Linked List"),
    ("remove-duplicates-from-sorted-list-ii", "Linked List"),
    ("rotate-list", "Linked List"),
    ("partition-list", "Linked List"),
    ("lru-cache", "Linked List"),
    # Binary Tree General
    ("maximum-depth-of-binary-tree", "Binary Tree General"),
    ("same-tree", "Binary Tree General"),
    ("invert-binary-tree", "Binary Tree General"),
    ("symmetric-tree", "Binary Tree General"),
    (
        "construct-binary-tree-from-preorder-and-inorder-traversal",
        "Binary Tree General",
    ),
    (
        "construct-binary-tree-from-inorder-and-postorder-traversal",
        "Binary Tree General",
    ),
    ("populating-next-right-pointers-in-each-node-ii", "Binary Tree General"),
    ("flatten-binary-tree-to-linked-list", "Binary Tree General"),
    ("path-sum", "Binary Tree General"),
    ("sum-root-to-leaf-numbers", "Binary Tree General"),
    ("binary-tree-maximum-path-sum", "Binary Tree General"),
    ("binary-search-tree-iterator", "Binary Tree General"),
    ("count-complete-tree-nodes", "Binary Tree General"),
    ("lowest-common-ancestor-of-a-binary-tree", "Binary Tree General"),
    # Binary Tree BFS
    ("binary-tree-right-side-view", "Binary Tree BFS"),
    ("average-of-levels-in-binary-tree", "Binary Tree BFS"),
    ("binary-tree-level-order-traversal", "Binary Tree BFS"),
    ("binary-tree-zigzag-level-order-traversal", "Binary Tree BFS"),
    # Binary Search Tree
    ("minimum-absolute-difference-in-bst", "Binary Search Tree"),
    ("kth-smallest-element-in-a-bst", "Binary Search Tree"),
    ("validate-binary-search-tree", "Binary Search Tree"),
    # Graph General
    ("number-of-islands", "Graph General"),
    ("surrounded-regions", "Graph General"),
    ("clone-graph", "Graph General"),
    ("evaluate-division", "Graph General"),
    ("course-schedule", "Graph General"),
    ("course-schedule-ii", "Graph General"),
    # Graph BFS
    ("snakes-and-ladders", "Graph BFS"),
    ("minimum-genetic-mutation", "Graph BFS"),
    ("word-ladder", "Graph BFS"),
    # Trie
    ("implement-trie-prefix-tree", "Trie"),
    ("design-add-and-search-words-data-structure", "Trie"),
    ("word-search-ii", "Trie"),
    # Backtracking
    ("letter-combinations-of-a-phone-number", "Backtracking"),
    ("combinations", "Backtracking"),
    ("permutations", "Backtracking"),
    ("combination-sum", "Backtracking"),
    ("n-queens-ii", "Backtracking"),
    ("generate-parentheses", "Backtracking"),
    ("word-search", "Backtracking"),
    # Divide & Conquer
    ("convert-sorted-array-to-binary-search-tree", "Divide & Conquer"),
    ("sort-list", "Divide & Conquer"),
    ("construct-quad-tree", "Divide & Conquer"),
    ("merge-k-sorted-lists", "Divide & Conquer"),
    # Kadane's Algorithm
    ("maximum-subarray", "Kadane's Algorithm"),
    ("maximum-sum-circular-subarray", "Kadane's Algorithm"),
    # Binary Search
    ("search-insert-position", "Binary Search"),
    ("search-a-2d-matrix", "Binary Search"),
    ("find-peak-element", "Binary Search"),
    ("search-in-rotated-sorted-array", "Binary Search"),
    ("find-first-and-last-position-of-element-in-sorted-array", "Binary Search"),
    ("find-minimum-in-rotated-sorted-array", "Binary Search"),
    ("median-of-two-sorted-arrays", "Binary Search"),
    # Heap
    ("kth-largest-element-in-an-array", "Heap"),
    ("ipo", "Heap"),
    ("find-k-pairs-with-smallest-sums", "Heap"),
    ("find-median-from-data-stream", "Heap"),
    # Bit Manipulation
    ("add-binary", "Bit Manipulation"),
    ("reverse-bits", "Bit Manipulation"),
    ("number-of-1-bits", "Bit Manipulation"),
    ("single-number", "Bit Manipulation"),
    ("single-number-ii", "Bit Manipulation"),
    ("bitwise-and-of-numbers-range", "Bit Manipulation"),
    # Math
    ("palindrome-number", "Math"),
    ("plus-one", "Math"),
    ("factorial-trailing-zeroes", "Math"),
    ("sqrtx", "Math"),
    ("powx-n", "Math"),
    ("max-points-on-a-line", "Math"),
    # 1D DP
    ("climbing-stairs", "1D DP"),
    ("house-robber", "1D DP"),
    ("word-break", "1D DP"),
    ("coin-change", "1D DP"),
    ("longest-increasing-subsequence", "1D DP"),
    # Multidimensional DP
    ("triangle", "Multidimensional DP"),
    ("minimum-path-sum", "Multidimensional DP"),
    ("unique-paths-ii", "Multidimensional DP"),
    ("longest-palindromic-substring", "Multidimensional DP"),
    ("interleaving-string", "Multidimensional DP"),
    ("edit-distance", "Multidimensional DP"),
    ("best-time-to-buy-and-sell-stock-iii", "Multidimensional DP"),
    ("best-time-to-buy-and-sell-stock-iv", "Multidimensional DP"),
    ("maximal-square", "Multidimensional DP"),
]

SQL_PROBLEMS: list[tuple[str, str]] = [
    # Select
    ("recyclable-and-low-fat-products", "Select"),
    ("find-customer-referee", "Select"),
    ("big-countries", "Select"),
    ("article-views-i", "Select"),
    ("invalid-tweets", "Select"),
    # Basic Joins
    ("replace-employee-id-with-the-unique-identifier", "Joins"),
    ("product-sales-analysis-i", "Joins"),
    ("customer-who-visited-but-did-not-make-any-transactions", "Joins"),
    ("rising-temperature", "Joins"),
    ("average-time-of-process-per-machine", "Joins"),
    ("employee-bonus", "Joins"),
    ("students-and-examinations", "Joins"),
    # Basic Aggregate Functions
    ("not-boring-movies", "Aggregation"),
    ("average-selling-price", "Aggregation"),
    ("project-employees-i", "Aggregation"),
    ("percentage-of-users-attended-a-contest", "Aggregation"),
    ("queries-quality-and-percentage", "Aggregation"),
    ("monthly-transactions-i", "Aggregation"),
    ("immediate-food-delivery-ii", "Aggregation"),
    ("game-play-analysis-iv", "Aggregation"),
    # Sorting and Grouping
    ("number-of-unique-subjects-taught-by-each-teacher", "Sorting & Grouping"),
    ("user-activity-for-the-past-30-days-i", "Sorting & Grouping"),
    ("product-sales-analysis-iii", "Sorting & Grouping"),
    ("classes-with-at-least-5-students", "Sorting & Grouping"),
    ("find-followers-count", "Sorting & Grouping"),
    # Advanced Select and Joins
    (
        "the-number-of-employees-which-report-to-each-employee",
        "Advanced Select & Joins",
    ),
    ("primary-department-for-each-employee", "Advanced Select & Joins"),
    ("triangle-judgement", "Advanced Select & Joins"),
    ("consecutive-numbers", "Advanced Select & Joins"),
    ("product-price-at-a-given-date", "Advanced Select & Joins"),
    ("last-person-to-fit-in-the-bus", "Advanced Select & Joins"),
    ("count-salary-categories", "Advanced Select & Joins"),
    # Subqueries
    ("employees-whose-manager-left-the-company", "Subqueries"),
    ("exchange-seats", "Subqueries"),
    ("movie-rating", "Subqueries"),
    ("restaurant-growth", "Subqueries"),
    ("friend-requests-ii-who-has-the-most-friends", "Subqueries"),
    ("investments-in-2016", "Subqueries"),
    ("department-top-three-salaries", "Subqueries"),
    # Advanced String Functions / Regex / Clause
    ("fix-names-in-a-table", "String Functions"),
    ("patients-with-a-condition", "String Functions"),
    ("delete-duplicate-emails", "String Functions"),
    ("second-highest-salary", "String Functions"),
    ("group-sold-products-by-the-date", "String Functions"),
    ("list-the-products-ordered-in-a-period", "String Functions"),
    ("find-users-with-valid-e-mails", "String Functions"),
    # Window Functions
    ("rank-scores", "Window Functions"),
    ("nth-highest-salary", "Window Functions"),
    ("department-highest-salary", "Window Functions"),
    ("managers-with-at-least-5-direct-reports", "Window Functions"),
]
