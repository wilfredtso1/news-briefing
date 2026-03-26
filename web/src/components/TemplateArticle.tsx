import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import TemplateFooter from './TemplateFooter.tsx'
import TemplateHeader from './TemplateHeader.tsx'
import Footer from './Footer.tsx'
import TemplateContentSection from './TemplateContentSection.tsx'


// Component

        function TemplateArticle({
            title
        }: {
            title: string;
        }) {
            return (
                <article className={"template_template__E5VkR"}>
                    <TemplateHeader title={title} />
                    <TemplateContentSection />
                    <TemplateFooter />
                </article>
            );
        }
    

export default TemplateArticle
