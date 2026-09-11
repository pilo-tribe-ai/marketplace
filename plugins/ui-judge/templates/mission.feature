# grounded-in: docs/user-guide.md#buying-an-item
# grounded-in-hash: 0000000000000000000000000000000000000000000000000000000000000000
# status: draft
@shopper
Feature: Checkout

  Scenario: A shopper buys one item
    Given I am signed in as a shopper
    When I find where the site lists things for sale
    And I add any item to my basket
    Then the basket shows one item
    When I go to the basket and begin checkout
    Then I see a total price
    When I pay with the test card
    Then the order is confirmed
    And the basket is empty

  Rule: never
    - an error in the browser console
    - a total of zero, blank, or "NaN"
