import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import TemplateScreenshotsTest from './TemplateScreenshotsTest.tsx'
import TemplateDescription from './TemplateDescription.tsx'


// Component
function TemplateContentSection() {
    return <section className={"template_templateContentContainer__Ov74t"}>
    	
            <TemplateScreenshotsTest />
        
    	
            <TemplateDescription
                description="Keep communication streamlined with an easy contact form that captures names, emails, and messages in one step. No more lost inquiries or scattered info."
                lastUpdatedLabel="Last updated last year"
            />
        
    </section>}


export default TemplateContentSection
