import functions_framework
import requests
import os
import re
import json
import base64
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from google.cloud import pubsub_v1

"""
The function is designed to synchronize products from CatalogIQ to Shopify using the new 2024-04 products API which allows a large number of options. However at time of testing my account was limited to 100 variants per product and 3 options.
It is offered as an example. Your actual implementation will vary. There are no warranties or guarantees provided with this code. It is provided as an example to help you get started with your own implementation.
The function will NOT check if the item already exists. It will create a new item each time it is called. You will need to add that logic if you want to check for existing items.
The function adds CatalogIQ product attributes as unstructured metafields in Shopify. You can modify this to suit your needs.
"""

publisher = pubsub_v1.PublisherClient()
# Add your project name and topic ID to the topic_path variable.
topic_path = publisher.topic_path('your-project', 'your-topic-id')

# Entry point for the function
# Our trigger function that will be called by Pub/Sub, we need to set that up in the GCP console when creating the function.
@functions_framework.cloud_event
def process_product(cloud_event):
    """Function to be triggered by Pub/Sub to process product synchronization."""
    data = base64.b64decode(cloud_event.data['message']['data']).decode('utf-8')
    data = json.loads(data)
    offset = int(data['offset'])
    sync_products(offset)


def publish_offset(offset):
    # Publish the updated offset to the Pub/Sub topic.
    message_json = json.dumps({'offset': str(offset)})  # Ensure offset is a string if your schema requires it
    message_bytes = message_json.encode('utf-8')
    publisher.publish(topic_path, message_bytes)

# Map the CatalogIQ product to Shopify product structure
def map_catalogiq_to_shopify(ciq_product):
    # Assuming 'options' represent product-wide options like size, color, etc.
    product_options = []
    option_names = set()

    # Collect unique option names and prepare productOptions structure
    for variant in ciq_product['variants']:
        for attribute in variant['attributes']:
            option_names.add(attribute['name'])

    # Map variants
    shopify_variants = []
    # At the time of publication the API only supports 100 variants per product
    for variant in ciq_product['variants'][:99]:
        option_values = []
        for option_name in option_names:
            # Find the corresponding attribute in the variant's attributes
            attribute_value = next((attr['value'] for attr in variant['attributes'] if attr['name'] == option_name), None)
            if attribute_value:
                option_values.append({"optionName": option_name, "name": attribute_value})

        shopify_variants.append({
            "sku": variant['default_code'],
            "optionValues": option_values
        })

    # Prepare productOptions structure with values
    product_options = []
    for option_name in option_names:
        values = []
        for variant in ciq_product['variants']:
            for attribute in variant['attributes']:
                if attribute['name'] == option_name:
                    values.append({"name": attribute['value']})
        
        # Make sure values contains unique values
        values = [dict(t) for t in {tuple(d.items()) for d in values}]

        product_options.append({
            "name": option_name,
            "values": values
        })     
    
    return {
        "title": ciq_product['name'],
        "vendor": "Vendor Name",
        "descriptionHtml": ciq_product.get('description_sale', ''),
        "productOptions": product_options,
        "variants": shopify_variants,
        "metafields": [{
            "namespace": attribute['category'],
            "description": attribute['description'],
            "key": attribute['name'],
            "value": attribute['value'],
            "type": "string"
                } for attribute in ciq_product['attributes'] if ciq_product['attributes']]        
    }

# GraphQL mutations to create a product and its images in Shopify
# https://shopify.dev/docs/api/admin-graphql/2024-04
def sync_products_to_shopify(shopify_graphql_url, shopify_headers, ciq_product):
    mapped_product = map_catalogiq_to_shopify(ciq_product)
    print(f"Product to be synced: {mapped_product}")
    # https://shopify.dev/docs/api/admin-graphql/2024-04/mutations/productSet
    mutation = '''
        mutation setProduct($input: ProductSetInput!) {
            productSet(input: $input, synchronous: true) {
                product { 
                    id
                }
                productSetOperation {
                    id
                    status
                userErrors {
                    code
                    field
                    message
                    }
                }
                userErrors {
                    field
                    message
                }
            }
        }
    '''
    response = requests.post(shopify_graphql_url, json={'query': mutation, 'variables': {'input': mapped_product}}, headers=shopify_headers)
    
    prod_response_json = response.json()

    try:
        # The product id is set in the mutation because synchronous is set to true
        # May need to check for progress of productSetOperation if synchronous is set to false and you are loading a large number of records
        product_id = prod_response_json['data']['productSet']['product']['id']
        
        # Add main image to product
        # https://shopify.dev/docs/api/admin-graphql/2024-04/mutations/productCreateMedia
        if ciq_product['main_image']:
            image_addition_query = """
                mutation productCreateMedia($media: [CreateMediaInput!]!, $productId: ID!) {
                    productCreateMedia(media: $media, productId: $productId) {
                        media {
                            alt
                            mediaContentType
                            status
                        }
                        mediaUserErrors {
                            field
                            message
                        }
                        product {
                            id
                            title
                        }
                    }
                }
            """
            image_data = {
                "media": [{
                    "alt": "Main Image",
                    "mediaContentType": "IMAGE",
                    "originalSource": ciq_product['main_image']
                }],
                "productId": product_id
            }
            main_image_response = requests.post(shopify_graphql_url, json={'query': image_addition_query, 'variables': image_data}, headers=shopify_headers)
        
        # Add additional images to the product
        if ciq_product['images']:
            for img in ciq_product['images']:
                image_addition_query = """
                    mutation productCreateMedia($media: [CreateMediaInput!]!, $productId: ID!) {
                        productCreateMedia(media: $media, productId: $productId) {
                            media {
                                alt
                            mediaContentType
                                status
                            }
                            mediaUserErrors {
                                field
                                message
                            }
                            product {
                                id
                                title
                            }
                        }
                    }                
                """
                alt_image_data = {
                    "media": [{
                        "alt": "Image",
                        "mediaContentType": "IMAGE",
                        "originalSource": img['url']
                    }],
                    "productId": product_id
                    }
                

                image_response = requests.post(shopify_graphql_url, json={'query': image_addition_query, 'variables': alt_image_data}, headers=shopify_headers)
                response_data = image_response.json()                
                if 'errors' in response_data:
                    print("Error adding image:", response_data['errors'])
                    continue  # Continue with next image if this fails
                if image_response.status_code != 200:
                    print("Failed to post data:", image_response.text)
                    continue  # Continue with next image if this fails
    except Exception as e:
        print("An error occurred:", str(e))
    
    return response.json()    



# Function to synchronize products from CatalogIQ to BigCommerce. 
# If the product name and/or SKU is already present it will skip the product.
def sync_products(offset):
    limit = 1

    # Retrieve API keys and endpoints from environment variables or add them here to debug/develop
    catalogiq_api_key = os.getenv('CATALOGIQ_API_KEY')
    sendgrid_api_key = os.getenv('SENDGRID_API_KEY')
    shopify_access_token = os.getenv('SHOPIFY_ACCESS_TOKEN') 

    catalogiq_endpoint = "https://catalogiq.app/api/v1/products"


    # Set your authorization headers for each API
    headers_catalogiq = {'Catalogiq-Api-Key': catalogiq_api_key}
    shopify_graphql_url = 'https://quickstart-0d328702.myshopify.com/admin/api/2024-04/graphql.json'
    shopify_headers = {
        'Content-Type': 'application/json',
        'X-Shopify-Access-Token':  access_token
    }    

    # Fetch products from CatalogIQ with the offset from Pub/Sub
    response_catalogiq = requests.get(f"{catalogiq_endpoint}?limit={limit}&offset={offset}", headers=headers_catalogiq)
    if response_catalogiq.status_code != 200:
        print(f"Error fetching product from CatalogIQ: {response_catalogiq.status_code} - {response_catalogiq.text}")
        return  # Consider adding error handling here, this will stop the function and not call the next record if there is an error. Monitor the logs for errors.

    product_data = response_catalogiq.json()
    products = product_data['results']

    # If there are no results from the API, we have reached the end of the catalog
    if not products:
        # Placeholder for any callback that you want to handle when the sync is complete
        send_completion_email(sendgrid_api_key)
        return "Sync Complete!"

    # Map the API properties and Post products to BigCommerce
    for product in products:              
        response_shopify = sync_products_to_shopify(shopify_graphql_url, shopify_headers, product)    
        #if response_shopify.data.productOperation.status not in ["COMPLETE"]:
        if response_shopify:
            print(f"Shopify Response: {response_shopify}")         

    # Update the offset in Pub/Sub to trigger the next invocation
    publish_offset(offset + 1)  # Update the offset for the next invocation
    return "Product Complete!"


# Add or update the sanitation of the input values from the dimensions above.
def clean_and_convert_to_float(input_value):
    if isinstance(input_value, int):
        return float(input_value)
    elif isinstance(input_value, str):
        cleaned_string = re.sub(r'[^0-9.]', '', input_value)
        return float(cleaned_string) if cleaned_string else 0.0
    else:
        return 0.00


# Callback at the end of the synchronization process to send an email notification
# You can change this to handle whatever you would like to do upon completion.
def send_completion_email(sendgrid_api_key):
    
    message = Mail(
        from_email='info@catalogiq.app', #Update with your from/to emails 
        to_emails='notify@catalogiq.app',
        subject='Brand Completed',
        html_content='The synchronization process for your products has been completed successfully.' #You can add more details here like the product name/id etc
    )
    try:
        sg = SendGridAPIClient(sendgrid_api_key)
        response = sg.send(message)
        print(f"Email sent! Status code: {response.status_code}")
    except Exception as e:
        print(f"An error sending mail occurred: {e}")
