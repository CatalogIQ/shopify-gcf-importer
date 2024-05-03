# Serverless Sync Connector to Shopify using Google Cloud

This tutorial outlines the process of syncing products from the CatalogIQ API to a Shopify store using Google Cloud Functions and the Pub/Sub messaging system. Our approach leverages Pub/Sub to efficiently handle large volumes of product data by queuing and processing one record at a time, thus preventing function timeouts.

For more information and the source code, visit our repository: [shopify-gdf-importer](https://github.com/CatalogIQ/shopify-gcf-importer).

## Requirements

- Google Cloud Console Developer Account with Billing Enabled
- Enabled Google Cloud services: Cloud Functions, Pub/Sub, and Cloud Run
- Basic knowledge of Python
- Shopify Store Account with API Key access

## Architecture Overview

The process is triggered by a Pub/Sub message containing an "offset" value, which then invokes the Cloud Function to sync a single product template at a time to Shopify. Upon completion, the function publishes a new message with an incremented offset to continue the process. 

## Usage Notes
- We are using the 2024-04 GraphQL API Release.
- The function is designed to synchronize products from CatalogIQ to Shopify using the new 2024-04 products API which allows a large number of options. However at time of testing my account was limited to 100 variants per product and 3 options.
- It is offered as an example. Your actual implementation will vary. There are no warranties or guarantees provided with this code. It is provided as an example to help you get started with your own implementation.
- The function will NOT check if the item already exists. It will create a new item each time it is called. You will need to add that logic if you want to check for existing items.
- The function adds CatalogIQ product attributes as unstructured metafields in Shopify. You can modify this to suit your needs.
- Shopify has Python Clients available that you can use to interact with the API. This example uses the requests library.
- You may need to throttle your API usage depending on your account and the number of products/variants you are syncing.

This setup is flexible and can be adapted to connect with other APIs like [BigCommerce](https://github.com/CatalogIQ/bigcommerce-gcf-importer), Salesforce, Odoo, or Microsoft Dynamics.

### Alternative Usage

You can modify this function to process specific records by `template_id`, making it possible to trigger imports directly from a Google Sheet containing product IDs and details via an HTTP function.


# Getting Started

## [Video ](https://catalogiq.app/slides/connector-examples-19)
View the connector example videos on [catalogiq.app courses](https://catalogiq.app/slides/connector-examples-19)

### Setting up Pub/Sub

1. Navigate to Pub/Sub in the Google Cloud Console.
2. Create a new topic.
3. Enter the desired topic name.
4. Add a schema with the property `offset` as a String.
5. Save your topic configuration.
6. Click "+Trigger Cloud Function" to connect your function.

### Configuring Cloud Function

1. Set the function name and runtime to Python 3.12.
2. Configure the number of messages to process at a time to `1`.
3. Visit the [project repository](https://github.com/CatalogIQ/shopify-gcf-importer).
4. In the Cloud Function Inline Editor, copy the contents of `Requirements.txt` and `Main.py` from the repository.5. 
6. Set the `entry_point` to `process_product`.
7. Set the following environment variables:
    - `CATALOGIQ_API_KEY`: Your CatalogIQ API key.
    - `BIGCOMMERCE_API_KEY`: Your BigCommerce API key.
    - `SHOPIFY_ACCESS_TOKEN`: Your Shopify access token.
    - `SENDGRID_API_KEY`: Your SendGrid API key for sending email notifications.
    - `SHOPIFY_STORE`: Your shopify store code/domain eg `quickstart-0d328702` not `quickstart-0d328702.myshopify.com`
8. Deploy the function.

### Testing

1. Navigate to Pub/Sub -> Topics -> Messages.
2. Publish a message with the message body `{ "offset": "0" }` to initiate syncing from the beginning of the list.
3. Go to Cloud Function, select your function, and check the Logs for debugging information.
4. Verify the addition of new products in your BigCommerce store.

## Support and Contributions

Contributions to this project are welcome! Feel free to fork the repository, make improvements, and submit pull requests.

## TODO
1. Verify message are not received more than once and make sure duplicates are not processed.


